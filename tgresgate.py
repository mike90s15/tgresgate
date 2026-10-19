#!/usr/bin/env python3
"""tgresgate — backup automático de canais do Telegram e restauração em um canal novo.

Salva cada post (texto formatado, fotos, vídeos, arquivos, álbuns e tópicos) num banco
SQLite local e, se o canal cair, cria outro e reposta tudo na mesma ordem.
Funciona com várias contas ao mesmo tempo sem salvar nada duas vezes.
"""
import argparse
import asyncio
import getpass
import json
import logging
import os
import sqlite3
import sys

try:
    from telethon import TelegramClient, events, functions, types, utils
except ImportError:
    sys.exit("Telethon não está instalado. Rode: pip install -r requirements.txt")

__version__ = "1.0.0"

APOIE = """
  Se o tgresgate te deu tranquilidade, ajude outros criadores a encontrá-lo:
    * siga @mike90s15 no Instagram: https://instagram.com/mike90s15
    * deixe uma estrela:  https://github.com/mike90s15/tgresgate
  Leva 10 segundos e é o que mantém o projeto vivo e atualizado.
"""

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PADRAO = os.path.join(BASE, "config.json")

log = logging.getLogger("tgresgate")
CFG = {}
DADOS = SESSOES = None
db = None
em_andamento = set()  # (canal, msg) sendo salvos agora, para duas contas não baixarem juntas


# ----------------------------------------------------------------------------- config / banco

def carregar_config(caminho):
    global CFG, DADOS, SESSOES
    if not os.path.exists(caminho):
        sys.exit(f"Arquivo de configuração não encontrado: {caminho}\n"
                 "Crie um com: python tgresgate.py configurar")
    with open(caminho, encoding="utf-8") as f:
        CFG = json.load(f)
    for chave in ("api_id", "api_hash", "contas", "canais"):
        if chave not in CFG:
            sys.exit(f"Falta '{chave}' em {caminho}. Veja o config.example.json")
    raiz = os.path.dirname(os.path.abspath(caminho))
    DADOS = os.path.join(raiz, CFG.get("pasta_backup", "backup"))
    SESSOES = os.path.join(raiz, CFG.get("pasta_sessoes", "sessoes"))
    os.makedirs(DADOS, exist_ok=True)
    os.makedirs(SESSOES, exist_ok=True)
    try:
        os.chmod(SESSOES, 0o700)  # as sessões dão acesso total às contas
    except OSError:
        pass
    abrir_banco()


def abrir_banco():
    global db
    db = sqlite3.connect(os.path.join(DADOS, "backup.db"))
    db.executescript("""
    CREATE TABLE IF NOT EXISTS canais (id INTEGER PRIMARY KEY, titulo TEXT, sobre TEXT, forum INT);
    CREATE TABLE IF NOT EXISTS progresso (canal_id INTEGER PRIMARY KEY, ultimo_id INT);
    CREATE TABLE IF NOT EXISTS topicos (canal_id INT, topico_id INT, titulo TEXT, cor INT,
        PRIMARY KEY (canal_id, topico_id));
    CREATE TABLE IF NOT EXISTS mensagens (canal_id INT, msg_id INT, data TEXT, topico_id INT,
        grupo INT, texto TEXT, midia TEXT, editado TEXT, salvo_por TEXT,
        PRIMARY KEY (canal_id, msg_id));
    CREATE TABLE IF NOT EXISTS acesso (canal_id INT, conta TEXT, PRIMARY KEY (canal_id, conta));
    CREATE TABLE IF NOT EXISTS mapa_topicos (origem INT, destino INT, topico_origem INT,
        topico_destino INT, PRIMARY KEY (origem, destino, topico_origem));
    CREATE TABLE IF NOT EXISTS repostados (origem INT, destino INT, msg_id INT,
        PRIMARY KEY (origem, destino, msg_id));
    """)
    for col in ("editado", "salvo_por"):  # bancos criados por versões antigas
        try:
            db.execute(f"ALTER TABLE mensagens ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass


# ----------------------------------------------------------------------------- contas

def novo_cliente(conta):
    c = TelegramClient(os.path.join(SESSOES, conta["nome"]),
                       int(conta.get("api_id", CFG["api_id"])), conta.get("api_hash", CFG["api_hash"]))
    c.flood_sleep_threshold = 3600  # se o Telegram mandar esperar, espera sozinho
    c.parse_mode = "html"  # texto salvo/reenviado em HTML mantém negrito, links etc.
    c.nome = conta["nome"]
    return c


def conta_por_nome(nome):
    if nome is None:
        return CFG["contas"][0]
    for conta in CFG["contas"]:
        if conta["nome"] == nome:
            return conta
    sys.exit(f"Conta '{nome}' não existe no config. Contas: {', '.join(x['nome'] for x in CFG['contas'])}")


async def conectar_todas():
    clientes = []
    for conta in CFG["contas"]:
        c = novo_cliente(conta)
        await c.connect()
        if await c.is_user_authorized():
            clientes.append(c)
        else:
            log.warning("conta %s sem login — rode: python tgresgate.py login", c.nome)
    if not clientes:
        sys.exit("Nenhuma conta logada. Rode: python tgresgate.py login")
    return clientes


# ----------------------------------------------------------------------------- backup

def eh_forum(ent):
    return bool(getattr(ent, "forum", False))


def topico_de(msg, forum):
    if not forum:
        return None
    r = msg.reply_to
    if r and getattr(r, "forum_topic", False):
        return r.reply_to_top_id or r.reply_to_msg_id
    return 1  # tópico "Geral"


async def canais_da_conta(c):
    """Canais que esta conta deve salvar: a lista do config ou "meus" (onde é dono/admin)."""
    achados = []
    if CFG["canais"] == "meus":
        async for d in c.iter_dialogs():
            e = d.entity
            if d.is_channel and (e.creator or e.admin_rights):
                achados.append(e)
    else:
        for ref in CFG["canais"]:
            try:
                achados.append(await c.get_entity(ref))
            except (ValueError, TypeError):
                pass  # esta conta não está nesse canal
    return achados


async def mapear(clientes):
    """canal_id -> [(cliente, entidade)], na ordem das contas do config."""
    mapa = {}
    for c in clientes:
        for ent in await canais_da_conta(c):
            cid = utils.get_peer_id(ent)
            mapa.setdefault(cid, []).append((c, ent))
            db.execute("INSERT OR IGNORE INTO acesso VALUES (?,?)", (cid, c.nome))
    db.commit()
    return mapa


async def registrar_canal(c, ent):
    full = await c(functions.channels.GetFullChannelRequest(ent))
    db.execute("INSERT OR REPLACE INTO canais VALUES (?,?,?,?)",
               (utils.get_peer_id(ent), ent.title, full.full_chat.about or "", int(eh_forum(ent))))
    db.commit()


async def salvar(c, cid, forum, msg):
    if isinstance(msg, types.MessageService):
        a = msg.action
        if isinstance(a, types.MessageActionTopicCreate):
            db.execute("INSERT OR REPLACE INTO topicos VALUES (?,?,?,?)",
                       (cid, msg.id, a.title, a.icon_color))
        elif isinstance(a, types.MessageActionTopicEdit) and a.title:
            db.execute("UPDATE topicos SET titulo=? WHERE canal_id=? AND topico_id=?",
                       (a.title, cid, topico_de(msg, forum)))
        db.commit()
        return False

    chave = (cid, msg.id)
    editado = msg.edit_date.isoformat() if msg.edit_date else None
    row = db.execute("SELECT editado FROM mensagens WHERE canal_id=? AND msg_id=?", chave).fetchone()
    if (row and row[0] == editado) or chave in em_andamento:
        return False  # outra conta já salvou (ou está salvando) esta mesma versão
    em_andamento.add(chave)
    try:
        midia = None
        if msg.photo or msg.document:
            pasta = os.path.join(DADOS, "midia", str(cid))
            os.makedirs(pasta, exist_ok=True)
            destino = os.path.join(pasta, f"{msg.id}{msg.file.ext or ''}")
            if not os.path.exists(destino):
                log.info("[%s] baixando mídia %s/%s", c.nome, cid, msg.id)
                if not await msg.download_media(file=destino):
                    destino = None
            if destino:
                midia = os.path.relpath(destino, DADOS)

        db.execute("INSERT OR REPLACE INTO mensagens VALUES (?,?,?,?,?,?,?,?,?)",
                   (cid, msg.id, msg.date.isoformat(), topico_de(msg, forum),
                    msg.grouped_id, msg.text or "", midia, editado, c.nome))
        db.commit()
        return True
    finally:
        em_andamento.discard(chave)


async def backup_canal(c, ent):
    cid, forum = utils.get_peer_id(ent), eh_forum(ent)
    await registrar_canal(c, ent)
    row = db.execute("SELECT ultimo_id FROM progresso WHERE canal_id=?", (cid,)).fetchone()
    n = 0
    async for msg in c.iter_messages(ent, reverse=True, min_id=row[0] if row else 0):
        if await salvar(c, cid, forum, msg):
            n += 1
        db.execute("INSERT OR REPLACE INTO progresso VALUES (?,?)", (cid, msg.id))
        db.commit()
    log.info("[%s] %s: %d mensagens novas", c.nome, ent.title, n)


async def backup_todos(mapa):
    """Cada canal é salvo por UMA conta; se ela falhar, a próxima que tem acesso assume."""
    for cid, acessos in mapa.items():
        for c, ent in acessos:
            try:
                await backup_canal(c, ent)
                break
            except Exception as e:
                log.warning("[%s] falhou em %s: %s — tentando outra conta", c.nome, cid, e)


# ----------------------------------------------------------------------------- restauração

async def criar_topico(c, dest, titulo, cor):
    upd = await c(functions.messages.CreateForumTopicRequest(peer=dest, title=titulo, icon_color=cor))
    for u in upd.updates:
        if isinstance(u, (types.UpdateNewChannelMessage, types.UpdateNewMessage)):
            return u.message.id
    raise RuntimeError(f"não consegui criar o tópico {titulo}")


async def restaurar(origem, destino, nome_conta, titulo_novo):
    canal = db.execute("SELECT titulo, sobre, forum FROM canais WHERE id=?", (origem,)).fetchone()
    if not canal:
        sys.exit(f"Canal {origem} não está no backup. Veja os IDs com: python tgresgate.py status")
    titulo, sobre, forum = canal
    intervalo = CFG.get("segundos_entre_posts", 3)

    c = novo_cliente(conta_por_nome(nome_conta))
    await c.start()
    log.info("Restaurando '%s' com a conta %s", titulo, c.nome)

    if destino is None:
        r = await c(functions.channels.CreateChannelRequest(
            title=titulo_novo or titulo, about=sobre, broadcast=not forum,
            megagroup=bool(forum), forum=bool(forum) or None))
        dest = r.chats[0]
        did = utils.get_peer_id(dest)
        log.info("Canal novo criado (ID %s)", did)
        log.info("Se parar no meio, continue com: python tgresgate.py restaurar %s %s --conta %s",
                 origem, did, c.nome)
    else:
        dest = await c.get_entity(destino)
        did = utils.get_peer_id(dest)

    mapa = {1: None}
    if forum:
        for tid, ttitulo, cor in db.execute(
                "SELECT topico_id, titulo, cor FROM topicos WHERE canal_id=? ORDER BY topico_id", (origem,)).fetchall():
            row = db.execute("SELECT topico_destino FROM mapa_topicos WHERE origem=? AND destino=? AND topico_origem=?",
                             (origem, did, tid)).fetchone()
            if row:
                mapa[tid] = row[0]
                continue
            novo = await criar_topico(c, dest, ttitulo, cor)
            mapa[tid] = novo
            db.execute("INSERT INTO mapa_topicos VALUES (?,?,?,?)", (origem, did, tid, novo))
            db.commit()
            log.info("  tópico criado: %s", ttitulo)
            await asyncio.sleep(intervalo)

    msgs = db.execute("""SELECT msg_id, topico_id, grupo, texto, midia FROM mensagens m
        WHERE canal_id=? AND NOT EXISTS (SELECT 1 FROM repostados r
            WHERE r.origem=m.canal_id AND r.destino=? AND r.msg_id=m.msg_id)
        ORDER BY msg_id""", (origem, did)).fetchall()

    # junta álbuns (várias fotos no mesmo post)
    blocos = []
    for m in msgs:
        if blocos and m[2] and blocos[-1][0][2] == m[2]:
            blocos[-1].append(m)
        else:
            blocos.append([m])

    log.info("Repostando %d mensagens em %d posts...", len(msgs), len(blocos))
    for i, bloco in enumerate(blocos, 1):
        topico = mapa.get(bloco[0][1]) if forum else None
        com_arquivo = [m for m in bloco if m[4] and os.path.exists(os.path.join(DADOS, m[4]))]
        if com_arquivo:
            arquivos = [os.path.join(DADOS, m[4]) for m in com_arquivo]
            textos = [m[3] for m in com_arquivo]
            await c.send_file(dest, arquivos if len(arquivos) > 1 else arquivos[0],
                              caption=textos if len(textos) > 1 else textos[0], reply_to=topico)
        elif bloco[0][3]:
            await c.send_message(dest, bloco[0][3], reply_to=topico)
        # (enquetes e outros tipos sem texto/arquivo são pulados)
        db.executemany("INSERT OR IGNORE INTO repostados VALUES (?,?,?)",
                       [(origem, did, m[0]) for m in bloco])
        db.commit()
        log.info("  %d/%d", i, len(blocos))
        await asyncio.sleep(intervalo)
    log.info("Pronto! Tudo repostado.")
    print(f"\nSeu canal voltou. Quantas horas de trabalho isso acabou de salvar?{APOIE}")


# ----------------------------------------------------------------------------- comandos

def cmd_configurar(caminho):
    print("Configuração do tgresgate\n")
    print("1) Entre em https://my.telegram.org > API development tools e crie um app.")
    api_id = input("   api_id: ").strip()
    api_hash = getpass.getpass("   api_hash (não aparece ao digitar): ").strip()
    nomes = input("\n2) Nomes curtos para suas contas, separados por vírgula [conta1]: ").strip() or "conta1"
    print("\n3) Quais canais salvar?\n"
          "   - Enter: todos em que alguma conta é dona ou admin\n"
          "   - ou digite @usuarios / IDs separados por vírgula")
    canais = input("   canais: ").strip()
    cfg = {
        "api_id": int(api_id),
        "api_hash": api_hash,
        "contas": [{"nome": n.strip()} for n in nomes.split(",") if n.strip()],
        "canais": "meus" if not canais else [int(x) if x.strip().lstrip("-").isdigit() else x.strip()
                                             for x in canais.split(",")],
        "segundos_entre_posts": 3,
    }
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    try:
        os.chmod(caminho, 0o600)
    except OSError:
        pass
    print(f"\nSalvo em {caminho}. Agora rode: python tgresgate.py login")
    print(APOIE)


async def cmd_login():
    for conta in CFG["contas"]:
        c = novo_cliente(conta)
        print(f"\n== Conta '{c.nome}' ==")
        await c.start()
        eu = await c.get_me()
        print(f"   ok, logado como {eu.first_name}")
        await c.disconnect()


async def cmd_listar():
    for c in await conectar_todas():
        print(f"\n== {c.nome} ==")
        async for d in c.iter_dialogs():
            if d.is_channel:
                tipo = "tópicos" if eh_forum(d.entity) else "canal" if getattr(d.entity, "broadcast", False) else "grupo"
                print(f"{d.id:>16}  [{tipo:^7}]  {d.name}")


async def cmd_backup():
    await backup_todos(await mapear(await conectar_todas()))


async def cmd_vigiar():
    clientes = await conectar_todas()
    mapa = await mapear(clientes)
    await backup_todos(mapa)
    forum_de = {cid: eh_forum(acessos[0][1]) for cid, acessos in mapa.items()}
    minutos = CFG.get("minutos_entre_varreduras", 15)

    for c in clientes:
        ents = [ent for acessos in mapa.values() for cc, ent in acessos if cc is c]
        if not ents:
            continue

        def handler(c=c):
            async def novo(ev):
                if await salvar(c, ev.chat_id, forum_de.get(ev.chat_id, False), ev.message):
                    log.info("[%s] post salvo %s/%s", c.nome, ev.chat_id, ev.message.id)
            return novo
        c.add_event_handler(handler(), events.NewMessage(chats=ents))
        c.add_event_handler(handler(), events.MessageEdited(chats=ents))

    async def varredura():  # pega tópicos novos, canais novos e qualquer coisa perdida
        while True:
            await asyncio.sleep(minutos * 60)
            try:
                await backup_todos(await mapear(clientes))
            except Exception as e:
                log.warning("varredura falhou: %s", e)

    log.info("Vigiando com %d conta(s), %d canal(is). Ctrl+C para parar.", len(clientes), len(mapa))
    asyncio.create_task(varredura())
    await asyncio.gather(*(c.run_until_disconnected() for c in clientes))


def cmd_status():
    canais = db.execute("SELECT id, titulo, forum FROM canais ORDER BY titulo").fetchall()
    if not canais:
        print("Nada salvo ainda. Rode: python tgresgate.py backup")
    for cid, titulo, forum in canais:
        n, nm = db.execute("SELECT COUNT(*), COUNT(midia) FROM mensagens WHERE canal_id=?", (cid,)).fetchone()
        nt = db.execute("SELECT COUNT(*) FROM topicos WHERE canal_id=?", (cid,)).fetchone()[0]
        contas = ", ".join(r[0] for r in db.execute("SELECT conta FROM acesso WHERE canal_id=?", (cid,)))
        print(f"{cid:>16}  {titulo}")
        print(f"{'':>16}  {n} mensagens ({nm} com mídia)" + (f", {nt} tópicos" if forum else "")
              + f" | contas: {contas or '-'}")


def main():
    p = argparse.ArgumentParser(
        prog="tgresgate", description="Backup automático de canais do Telegram e restauração em um canal novo.")
    p.add_argument("-c", "--config", default=CONFIG_PADRAO, help="caminho do config.json")
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", metavar="comando")
    sub.add_parser("configurar", help="cria o config.json respondendo perguntas")
    sub.add_parser("login", help="faz login em cada conta (só na primeira vez)")
    sub.add_parser("listar", help="mostra os canais de cada conta, com os IDs")
    sub.add_parser("backup", help="salva o que falta e termina")
    sub.add_parser("vigiar", help="backup + fica ligado salvando cada post novo")
    sub.add_parser("status", help="mostra o que já foi salvo")
    r = sub.add_parser("restaurar", help="cria um canal novo e reposta tudo do backup")
    r.add_argument("origem", type=int, help="ID do canal antigo (veja em 'status')")
    r.add_argument("destino", type=int, nargs="?", help="ID de um canal já existente para continuar/usar")
    r.add_argument("--conta", help="conta que vai criar e postar (padrão: a primeira)")
    r.add_argument("--titulo", help="nome do canal novo (padrão: o mesmo do antigo)")
    a = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    logging.getLogger("telethon").setLevel(logging.WARNING)

    if not a.cmd:
        p.print_help()
        return
    if a.cmd == "configurar":
        return cmd_configurar(a.config)
    carregar_config(a.config)
    if a.cmd == "status":
        return cmd_status()
    acoes = {
        "login": cmd_login, "listar": cmd_listar, "backup": cmd_backup, "vigiar": cmd_vigiar,
        "restaurar": lambda: restaurar(a.origem, a.destino, a.conta, a.titulo),
    }
    try:
        asyncio.run(acoes[a.cmd]())
    except KeyboardInterrupt:
        print("\nParado.")


if __name__ == "__main__":
    main()
