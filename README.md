# tgresgate

**Backup automático dos seus canais do Telegram. Se um canal cair, você cria outro e reposta tudo com um comando só.**

Quem vende conteúdo, dá cursos ou mantém comunidade no Telegram costuma ter tudo num lugar só. Se o canal for derrubado, se você perder o número ou se a conta for banida, o material some junto. O tgresgate guarda uma cópia de cada post **fora do Telegram**, no seu computador, servidor ou celular, e consegue recriar o canal inteiro a partir dela.

> 🇺🇸 *English summary at the end.*

---

## O que ele faz

- **Salva tudo:** texto com formatação (negrito, links...), fotos, vídeos, arquivos, áudios, álbuns e **tópicos** (grupos com tópicos/fórum).
- **Salva na hora:** no modo `vigiar` ele fica ligado e guarda cada post assim que você publica, inclusive edições.
- **Restaura com um comando:** cria um canal novo com o mesmo nome e descrição, recria os tópicos e reposta tudo **na ordem original e no tópico certo**.
- **Retoma de onde parou:** se cair a internet no meio do backup ou da restauração, é só rodar de novo. Nada é duplicado.
- **Funciona com várias contas:** coloque 2, 3, 6 contas. Se várias estão no mesmo canal, cada post é salvo **uma vez só**. Se uma conta cair, outra assume sozinha.
- **Não depende da conta original:** perdeu o número? Faça login com uma conta nova e restaure a partir da pasta de backup.
- Funciona no **Linux, Windows, macOS e Android (Termux)**, e roda 24h como serviço do systemd.

## Gostou? Me ajude a continuar

Pense no dia em que seu canal cair: anos de posts, aulas e clientes voltando ao ar com um único comando. O tgresgate é gratuito e vai continuar assim, mas ele só melhora se mais gente souber que ele existe.

Se ele te deu essa tranquilidade, retribua em 10 segundos:

- 📸 **Siga [@mike90s15 no Instagram](https://instagram.com/mike90s15)** para novidades, dicas de proteção de canais e as próximas ferramentas.
- ⭐ **Deixe uma estrela aqui no GitHub.** Ela faz o projeto aparecer para outros criadores que ainda correm o risco de perder tudo.

Cada seguidor e cada estrela são o sinal de que vale a pena continuar atualizando.

## Índice

1. [Instalação](#1-instalação)
2. [Configuração](#2-configuração)
3. [Uso](#3-uso)
4. [Restaurar um canal que caiu](#4-restaurar-um-canal-que-caiu)
5. [Deixar rodando 24h (servidor / systemd)](#5-deixar-rodando-24h-servidor--systemd)
6. [Guardar o backup em outro lugar](#6-guardar-o-backup-em-outro-lugar-importante)
7. [Segurança](#7-segurança)
8. [Limitações](#8-limitações)
9. [Perguntas frequentes](#9-perguntas-frequentes)

---

## 1. Instalação

Precisa do **Python 3.8 ou mais novo**.

### Linux, macOS ou Termux (Android)

```bash
git clone https://github.com/mike90s15/tgresgate.git tgresgate
cd tgresgate
./instalar.sh
```

No Termux, instale o git antes: `pkg install git`.

### Windows

Instale o Python em [python.org](https://www.python.org/downloads/) e marque **"Add Python to PATH"** durante a instalação. Depois, no PowerShell, dentro da pasta do projeto:

```powershell
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

*Dica:* `pip install cryptg` deixa os downloads bem mais rápidos (opcional).

No Windows, troque `./venv/bin/python` por `venv\Scripts\python` em todos os comandos abaixo.

## 2. Configuração

### 2.1 Pegue sua chave de API (grátis, 2 minutos)

1. Entre em **https://my.telegram.org** com seu número.
2. Clique em **API development tools**.
3. Preencha *App title* e *Short name* com qualquer nome (ex.: `meubackup`) e clique em **Create application**.
4. Anote o **api_id** (um número) e o **api_hash** (um código longo).

Uma única chave serve para todas as suas contas.

### 2.2 Crie o arquivo de configuração

O jeito fácil é responder as perguntas:

```bash
./venv/bin/python tgresgate.py configurar
```

Se preferir editar à mão, copie `config.example.json` para `config.json`:

```json
{
  "api_id": 1234567,
  "api_hash": "0123456789abcdef0123456789abcdef",
  "contas": [
    {"nome": "principal"},
    {"nome": "reserva"}
  ],
  "canais": "meus",
  "segundos_entre_posts": 3,
  "minutos_entre_varreduras": 15
}
```

| Campo | O que é |
|---|---|
| `api_id`, `api_hash` | A chave do passo 2.1. |
| `contas` | Um apelido para cada conta do Telegram que vai ser usada. O apelido é só para você identificar. |
| `canais` | `"meus"` salva todo canal/grupo em que alguma conta é **dona ou admin**. Para escolher, use uma lista: `["@meucanal", -1001234567890]`. |
| `segundos_entre_posts` | Pausa entre posts na restauração. Valores muito baixos podem fazer o Telegram bloquear a conta por spam. |
| `minutos_entre_varreduras` | No modo `vigiar`, a cada quantos minutos ele confere se passou algo (tópicos novos, canais novos). |
| `pasta_backup`, `pasta_sessoes` | *(opcional)* Onde guardar o backup e os logins. O padrão é `backup/` e `sessoes/`. |

Uma conta pode ter api_id/api_hash próprios: `{"nome": "x", "api_id": 111, "api_hash": "..."}`.

### 2.3 Faça login nas contas

```bash
./venv/bin/python tgresgate.py login
```

Ele pede, para cada conta, o número (com DDI, ex.: `+5511999998888`), o código que chega no app do Telegram e a senha de duas etapas, se tiver. **Só precisa fazer uma vez.**

## 3. Uso

| Comando | O que faz |
|---|---|
| `tgresgate.py listar` | Mostra os canais/grupos de cada conta, com os IDs. |
| `tgresgate.py backup` | Salva tudo o que ainda não foi salvo e termina. Na primeira vez baixa o histórico inteiro. |
| `tgresgate.py vigiar` | Faz o backup e **fica ligado**, salvando cada post novo na hora. |
| `tgresgate.py status` | Mostra o que já está salvo de cada canal. |
| `tgresgate.py restaurar <ID>` | Cria um canal novo e reposta tudo. Veja a seção 4. |

(Sempre com `./venv/bin/python` na frente.)

Exemplo do `status`:

```
  -1001234567890  Curso de Violão
                  1840 mensagens (1203 com mídia), 12 tópicos | contas: principal, reserva
```

### Onde ficam os arquivos

```
backup/
├── backup.db            ← banco SQLite com textos, tópicos e quem salvou cada post
└── midia/
    └── -1001234567890/  ← uma pasta por canal
        ├── 15.jpg
        ├── 16.mp4
        └── ...
sessoes/                 ← logins das contas (NÃO compartilhe)
```

O `backup.db` é um SQLite comum e abre em qualquer visualizador, como o [DB Browser for SQLite](https://sqlitebrowser.org/).

### Como ele evita salvar duas vezes

Cada post é identificado pelo **ID do canal + ID da mensagem**. Antes de salvar, ele confere se aquele post (naquela versão, caso tenha sido editado) já está no banco. Por isso:

- se 3 contas estão no mesmo canal, o post é salvo uma vez e a mídia é baixada uma vez;
- o histórico de cada canal é baixado por uma conta só. Se ela falhar, a próxima que está no canal assume;
- a coluna `salvo_por` mostra qual conta salvou cada post, e a tabela `acesso` mostra quais contas estão em cada canal.

## 4. Restaurar um canal que caiu

1. Veja o ID do canal antigo:
   ```bash
   ./venv/bin/python tgresgate.py status
   ```
2. Restaure:
   ```bash
   ./venv/bin/python tgresgate.py restaurar -1001234567890
   ```
   Ele cria o canal novo (normal ou com tópicos, igual ao original), recria os tópicos e reposta tudo.

Opções:

- `--conta reserva` usa outra conta para criar e postar (útil se a principal caiu).
- `--titulo "Novo nome"` dá outro nome ao canal novo.
- **Se parar no meio**, ele mostra o comando para continuar, com o ID do canal novo:
  ```bash
  ./venv/bin/python tgresgate.py restaurar -1001234567890 -1009876543210
  ```
  Esse formato também serve para repostar num canal que você já criou à mão.

> **Tempo:** com a pausa padrão de 3 s, 1.000 posts levam cerca de 50 minutos. Se o Telegram pedir para esperar (*flood wait*), o programa espera sozinho e continua.

> **Perdeu o número?** Crie uma conta nova, coloque-a no `config.json`, rode `login` e depois `restaurar`. Basta ter a pasta `backup/`.

## 5. Deixar rodando 24h (servidor / systemd)

Num servidor Linux (VPS, Raspberry Pi, PC sempre ligado):

```bash
# 1. baixar em /opt/tgresgate, com um usuário só para ele
sudo git clone https://github.com/mike90s15/tgresgate.git /opt/tgresgate
sudo useradd -r -d /opt/tgresgate tgresgate
sudo chown -R tgresgate: /opt/tgresgate
cd /opt/tgresgate
sudo -u tgresgate ./instalar.sh

# 2. configurar e fazer login (uma vez)
sudo -u tgresgate ./venv/bin/python tgresgate.py configurar
sudo -u tgresgate ./venv/bin/python tgresgate.py login

# 3. ativar o serviço
sudo cp deploy/tgresgate.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tgresgate
```

Comandos úteis:

```bash
journalctl -u tgresgate -f          # ver o que está acontecendo
sudo systemctl restart tgresgate    # reiniciar
sudo systemctl stop tgresgate       # parar
```

Se o programa cair, o systemd religa sozinho em 30 segundos.

> **Antes de restaurar, pare o serviço** (`sudo systemctl stop tgresgate`). Os dois usam o mesmo login, e rodar ao mesmo tempo pode dar erro de sessão.

### No Android (Termux)

```bash
termux-wake-lock                       # impede o Android de pausar o Termux
./venv/bin/python tgresgate.py vigiar
```

Desative também a otimização de bateria do Termux nas configurações do Android.

## 6. Guardar o backup em outro lugar (importante!)

Se o backup fica só no mesmo aparelho, perder o aparelho é perder tudo. Copie a pasta `backup/` para outro lugar com frequência.

**Com rclone (Google Drive, Dropbox, OneDrive, S3...):**

```bash
# configure uma vez (siga as perguntas e dê o nome "drive")
rclone config

# copie (só envia o que mudou)
rclone sync backup/ drive:tgresgate
```

Para fazer isso todo dia às 3h, adicione no `crontab -e`:

```
0 3 * * * cd /opt/tgresgate && rclone sync backup/ drive:tgresgate
```

**No Termux:** rode `termux-setup-storage` e copie para a memória do celular, de onde um app como o Google Drive ou o Autosync pode enviar:

```bash
cp -r backup/ ~/storage/shared/tgresgate/
```

## 7. Segurança

- 🔒 **A pasta `sessoes/` dá acesso total às suas contas.** Quem tiver esses arquivos consegue ler e mandar mensagens como você. Nunca envie para ninguém, nem para o GitHub. O `.gitignore` já impede isso.
- 🔒 **Não compartilhe o `config.json`.** Ele contém seu `api_hash`.
- Ative a **verificação em duas etapas** em todas as contas (Configurações → Privacidade e Segurança).
- Coloque uma **segunda conta como administradora** dos canais importantes. Se uma cair, a outra continua com o canal.
- O programa só **lê** os canais durante o backup. Ele só posta algo quando você roda `restaurar`.

## 8. Limitações

- Os posts restaurados ficam com a **data de hoje**. O Telegram não permite postar com data antiga.
- **Enquetes, localizações e contatos** não são repostados. Texto, fotos, vídeos, arquivos, áudios, stickers e álbuns são.
- Reações, comentários e visualizações não são salvos.
- Arquivos muito grandes (vídeos de vários GB) demoram para baixar e ocupam espaço. Confira o disco.
- O Telegram limita o ritmo de postagem. Restaurar canais enormes leva horas, mas o programa espera e continua sozinho.

## 9. Perguntas frequentes

**Precisa ser dono do canal?**
Para fazer backup, basta a conta conseguir ver o canal. Com `"canais": "meus"`, ele pega os canais onde alguma conta é dona ou admin. Para outros, liste-os no config.

**Funciona com bot em vez de conta?**
Não. Bots não conseguem ler o histórico antigo nem criar canais e tópicos. Por isso o programa usa contas normais (via [Telethon](https://github.com/LonamiWebs/Telethon)).

**Minha conta pode ser banida por usar isso?**
O backup só faz leituras normais, como o próprio app faz. Na restauração, mantenha `segundos_entre_posts` em 3 ou mais para não parecer spam.

**Parei o programa no meio. Perdi algo?**
Não. Rode o mesmo comando de novo e ele continua de onde parou.

**Posso usar o mesmo backup em outro computador?**
Sim. Copie a pasta inteira, faça `login` lá e pronto.

---

## English summary

**tgresgate** continuously backs up Telegram channels and forum groups (text with formatting, media, albums and topics) to a local SQLite database plus a media folder, and can **recreate a lost channel** by reposting everything in order, with topics, using any account.

- Multiple accounts, one shared database, no duplicates: each message is keyed by channel and message ID, and if one account loses access another takes over.
- `vigiar` mode saves every new or edited post in real time. Runs on Linux (systemd unit in `deploy/`), Windows, macOS and Android/Termux.
- Backup and restore resume where they stopped.

```bash
./instalar.sh
./venv/bin/python tgresgate.py configurar   # api_id/api_hash from my.telegram.org
./venv/bin/python tgresgate.py login
./venv/bin/python tgresgate.py vigiar       # or: backup / status / restaurar <channel_id>
```

## Licença

[MIT](LICENSE). Use, modifique e distribua à vontade.
