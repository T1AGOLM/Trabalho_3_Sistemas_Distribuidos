# 🎧 AudioLayers — Sistema Cliente/Servidor em Camadas para Processamento de Áudio

**Trabalho 03 — Arquiteturas: Sistema em Camadas**

Sistema distribuído em **três camadas** capaz de enviar, processar (FFmpeg) e armazenar
arquivos de áudio de forma organizada, com metadados em banco de dados e interface web
para reprodução pelo navegador.

```
┌─────────────────────┐   HTTP (multipart)   ┌──────────────────────────┐   SQLAlchemy   ┌──────────────┐
│  1. CLIENTE (GUI)   │ ───────────────────▶ │  2. SERVIDOR             │ ─────────────▶ │  3. BANCO    │
│  PySide6 (Qt6)      │ ◀─────────────────── │  FastAPI + FFmpeg        │                │  PostgreSQL  │
│  desktop do usuário │   JSON / áudio       │  + interface web própria │                │  tabela      │
└─────────────────────┘                      └────────────┬─────────────┘                │  audios      │
                                                          │ arquivos                     └──────────────┘
                                                          ▼
                                            data/storage/AAAA/MM/DD/<uuid>/
```

---

## ✨ Funcionalidades

### Cliente gráfico (PySide6)
- Seleção de arquivo de áudio (mp3, wav, ogg, flac, m4a, aac, opus…)
- Envio via HTTP indicando o **processamento desejado**
- **Reprodução** do áudio **original** e do **processado** (QMediaPlayer)
- **Histórico** de arquivos enviados, com filtro por nome
- **Informações do áudio**: duração, formato, tamanho, sample rate, canais, bitrate
- Visualização da **forma de onda** (waveform.png gerada pelo servidor)
- Indicador de conexão com o servidor e com o banco de dados

### Servidor (FastAPI + FFmpeg)
- Recebe uploads via `POST /api/audios/upload` (streaming, com limite de tamanho)
- **Processamentos disponíveis:**

  | Processamento      | Descrição                                    | Parâmetros            |
  |--------------------|----------------------------------------------|-----------------------|
  | `normalize`        | Normalização de volume (EBU R128 `loudnorm`) | —                     |
  | `mono`             | Conversão para mono (`-ac 1`)                | —                     |
  | `speed`            | Altera a velocidade (mantém o pitch)         | `rate` (0.25–4.0)     |
  | `bitrate`          | Redução da taxa de bits                      | `kbps` (16–320)       |
  | `convert`          | Conversão de formato                         | `target_ext` (ogg, mp3, flac, wav, m4a, opus) |

- Armazenamento organizado por **data + UUID** (ver Regras abaixo)
- **meta.json** com checksum SHA-256, parâmetros usados e tamanhos
- **waveform.png** gerada automaticamente (FFmpeg → PCM → Pillow)
- Diretório **trash/** para arquivos marcados para exclusão
- **Interface web** em `http://localhost:8000/` para listar e reproduzir os áudios

### Banco de dados (PostgreSQL)
Tabela `audios` (ver `db/init.sql`):

| Campo             | Tipo            | Descrição                        |
|-------------------|-----------------|----------------------------------|
| `id`              | UUID (PK)       | identificador único do áudio     |
| `original_name`   | VARCHAR(255)    | nome original do arquivo         |
| `original_ext`    | VARCHAR(16)     | extensão original                |
| `mime_type`       | VARCHAR(100)    | MIME type                        |
| `size_bytes`      | BIGINT          | tamanho do upload                |
| `duration_sec`    | DOUBLE PRECISION| duração em segundos              |
| `sample_rate`     | INTEGER         | taxa de amostragem (Hz)          |
| `channels`        | INTEGER         | nº de canais                     |
| `bitrate`         | INTEGER         | taxa de bits (kbps)              |
| `processing_type` | VARCHAR(50)     | none / normalize / mono / ...    |
| `created_at`      | TIMESTAMPTZ     | data/hora do envio               |
| `path_original`   | VARCHAR(500)    | caminho relativo do original     |
| `path_processed`  | VARCHAR(500)    | caminho relativo do processado   |

---

## 📁 Regras de armazenamento

```
data/storage/
├── 2026/09/14/                      ← ano/mês/dia do envio
│   └── 3f2c9a1e-8b4d-4c6e-9f0a-…/   ← UUID único do áudio
│       ├── audio.mp3                ← original (sempre audio.{ext})
│       ├── audio_processed.ogg      ← processado (se houver)
│       ├── meta.json                ← checksum, parâmetros, tamanhos
│       └── waveform.png             ← forma de onda
└── trash/                           ← registros marcados para exclusão
    └── 3f2c9a1e-8b4d-…/
```

- Cada arquivo recebe um **UUID único**; o nome armazenado é sempre `audio.{ext}`
- Metadados complementares em **meta.json** (checksum SHA-256, parâmetros do processamento, tamanhos)
- **waveform.png** gerada automaticamente para visualização rápida
- **trash/** armazena temporariamente arquivos marcados para exclusão

---

## 🚀 Instalação

Requisitos: **Python 3.10+** e **FFmpeg** instalado no servidor (`ffmpeg`/`ffprobe` no PATH).

```bash
# 1. clonar o repositório
git clone <url-do-repositorio>
cd Trabalho_3_Sistemas_Inteligentes

# 2. criar ambiente virtual e instalar dependências
python -m venv .venv
source .venv/bin/activate          # Linux/macOS  (Windows: .venv\Scripts\activate)
pip install -r requirements.txt

# 3. configurar variáveis de ambiente (opcional)
cp .env.example .env               # ajuste DATABASE_URL, PORT, STORAGE_DIR se necessário
```

---

## 🗄️ Banco de dados

**Opção A — Docker (recomendada):**

```bash
docker compose up -d               # PostgreSQL 16 em localhost:5432
# credenciais: audio_user / audio_pass / audio_db (ver docker-compose.yml)
```

O script `db/init.sql` é executado automaticamente na inicialização do container.

**Opção B — PostgreSQL local:**

```bash
createdb audio_db
psql -d audio_db -f db/init.sql
```

> 💡 **Fallback automático:** se o PostgreSQL estiver inacessível, o servidor usa um
> banco SQLite local (`data/audio_fallback.db`) sem nenhuma alteração de código —
> útil para demonstrações rápidas. O badge na interface web mostra qual banco está em uso.

---

## ▶️ Execução do servidor (IPv6 + IPv4, igual em qualquer máquina)

```bash
source .venv/bin/activate
python -m server
```

É **o mesmo comando no Linux, Windows e macOS**. O `python -m server` cria um
socket **dual-stack** (`IPV6_V6ONLY=0`): escuta **IPv6 e IPv4 ao mesmo tempo**, na
mesma porta — se a rede não tiver IPv6, a conexão cai no IPv4 sem mudar nada.

- **Interface web:** http://localhost:8000/ (ou `http://[::1]:8000/`)
- **Documentação interativa (Swagger):** http://localhost:8000/docs

No startup, o servidor imprime os endereços para usar no cliente, ex.:

```
[servidor] escutando em :: + 0.0.0.0 (IPv6 e IPv4), porta 8000
[servidor] nesta máquina:  http://localhost:8000
[servidor] nome mDNS:      http://note-a.local:8000   ← endereço fixo para o cliente (não muda com a rede)
[servidor] IPv6:           http://[fe80::1a2b:3c4d:5e6f:7788%25wlan0]:8000
[servidor] IPv4:           http://192.168.0.42:8000
```

> ⚠️ **Por que não `uvicorn --host 0.0.0.0` nem `--host ::`?** O `0.0.0.0` é só
> IPv4; e o `::` do uvicorn só aceita IPv4 junto no Linux/macOS — no **Windows**
> o socket nasce com `IPV6_V6ONLY=1` e ficaria **somente IPv6**. O launcher
> `python -m server` força o dual-stack via `setsockopt`, ficando **idêntico em
> qualquer SO**.

Alternativa (comportamento padrão do uvicorn, sem dual-stack garantido):

```bash
uvicorn server.main:app --host :: --port 8000   # no Windows fica só IPv6!
```

### Liberar a porta 8000 no firewall do servidor

Se o cliente não conecta, libere a porta no firewall da máquina do **servidor**:

```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 8000/tcp

# Fedora/RHEL (firewalld)
sudo firewall-cmd --add-port=8000/tcp --permanent && sudo firewall-cmd --reload

# Windows (PowerShell como administrador)
netsh advfirewall firewall add rule name="AudioLayers 8000" dir=in action=allow protocol=TCP localport=8000
```

## ▶️ Execução do cliente (sem descobrir IP de nada)

Em **outra máquina** (ou na mesma), use **o nome da máquina do servidor** em vez
de IP — é o mesmo comando em qualquer SO e em qualquer rede:

```bash
source .venv/bin/activate
python -m client.main --server "http://NOME-DO-SERVIDOR.local:8000"
# ex.: python -m client.main --server "http://note-a.local:8000"

# sem --server, conecta em http://127.0.0.1:8000 (servidor na mesma máquina)
```

O nome é o **hostname do servidor + `.local`** (mDNS/Bonjour/Avahi, ativo por
padrão em Windows 10+, macOS e na maioria dos Linuxes com systemd). Descubra com
`hostname` na máquina do servidor. **Vantagens:** não muda quando a rede muda, não
importa se a rede usa IPv4 ou IPv6, e nunca precisa rodar `ipconfig`/`ip addr`.

> 💡 **Fallback automático no cliente:** se o `.local` não responder, o cliente
> tenta sozinho o endereço IPv6/IPv4 literal do hostname informado e o `::1` —
> nenhum lado precisa "descobrir" o endereço do outro manualmente.

Formas alternativas de `--server` (todas com colchetes em IPv6):

| Forma | Exemplo | Quando usar |
|-------|---------|-------------|
| mDNS (recomendada) | `http://note-a.local:8000` | sempre; imune a troca de rede/IP |
| IPv6 link-local | `http://[fe80::1a2b:3c4d:5e6f:7788%25wlan0]:8000` | rede sem mDNS; `%25` + interface no lugar da zona |
| IPv6 global/ULA | `http://[2001:db8::10]:8000` | redes com endereços globais; sem zona |
| IPv4 | `http://192.168.0.42:8000` | redes só IPv4 |

Opções do cliente:

| Opção        | Descrição                                        | Padrão                |
|--------------|--------------------------------------------------|-----------------------|
| `--server`   | URL do servidor (mDNS, IPv6 ou IPv4)             | `http://127.0.0.1:8000` |
| `--timeout`  | Timeout de rede em segundos (upload/processamento) | `120`               |

---

## 🌐 Demonstração com duas máquinas (cliente e servidor)

O trabalho exige **dois computadores distintos**. Com IPv6 + mDNS o passo a passo
fica curto — **nenhuma máquina precisa descobrir o endereço da outra**:

1. **Máquina A (servidor):** suba o banco e o servidor:
   ```bash
   docker compose up -d
   python -m server
   ```
   O startup imprime o nome mDNS (ex.: `http://note-a.local:8000`) — e confirme
   que a porta 8000 está liberada no firewall.

2. **Teste rápido:** na **Máquina B**, abra no navegador
   `http://note-a.local:8000/health` — deve responder `{"status":"ok",...}`.
   Se não abrir, veja *Solução de problemas* abaixo antes de usar o cliente.

3. **Máquina B (cliente):** instale as dependências (`pip install -r requirements.txt`)
   e execute:
   ```bash
   python -m client.main --server "http://note-a.local:8000"
   ```

4. Siga o fluxo de demonstração da seção seguinte (enviar, processar,
   reproduzir, histórico, banco, organização de arquivos, interface web).

### Solução de problemas — timeout ao enviar

O cliente mostra mensagens detalhadas indicando a causa provável. As mais comuns:

| Sintoma | Causa provável | Solução |
|---------|----------------|---------|
| *"tempo esgotado ao conectar"* | servidor fora do ar, firewall ou Wi-Fi com isolamento de clientes | verifique `/health` no navegador; libere a porta 8000; conecte as duas máquinas em outro Wi-Fi/hotspot celular |
| *"conexão caiu durante o envio"* | rede lenta/instável com arquivo grande | aumente o timeout: `python -m client.main --timeout 300` |
| *"recebeu o arquivo mas demorou para responder"* | processamento FFmpeg de áudio longo | aumente o timeout: `--timeout 300` |
| `.local` não resolve | mDNS desativado/bloqueado na rede | Linux: `sudo apt install avahi-daemon`; senão use o IPv6 literal impresso no startup do servidor |
| conecta na mesma máquina, mas não de outra | servidor rodando em `127.0.0.1` | use `python -m server` (escuta em `::` + `0.0.0.0`) |
| Wi-Fi da universidade | **ap/client isolation** bloqueia tráfego entre máquinas | use hotspot do celular ou um roteador próprio |

Dica de rede: teste a conectividade básica antes da demo
`ping note-a.local` e `curl http://note-a.local:8000/health`.

---

## 🌐 Rodando via IPv6 (endereços literais, quando o mDNS não está disponível)

Se a rede bloqueia mDNS, use o **endereço IPv6 link-local** da máquina do servidor
— ele existe em toda interface de rede moderna (`fe80::/10`) e nunca depende de
IPv4 ou DHCP.

### 1. Pegue o IPv6 do servidor (apenas uma vez, na máquina A)

O startup do `python -m server` **já imprime** os endereços em IPv6 e IPv4. Para
ver manualmente:

```bash
# Linux / macOS
ip -6 addr show scope link          # Linux (procure por inet6 fe80::…)
ifconfig | grep inet6               # macOS/Linux BSD

# Windows (PowerShell ou cmd)
ipconfig                            # procure por "Endereço IPv6 link-local"
```

> 💡 Cada interface (Wi-Fi `wlan0`, cabo `eth0`, etc.) tem um endereço link-local
> próprio — use o da interface conectada à rede entre as duas máquinas.

### 2. Libere a porta 8000 no firewall (mesmos comandos da seção anterior)

### 3. Servidor

O mesmo `python -m server` da seção anterior — ele **já escuta IPv6 e IPv4**
(dual-stack). Não há comando diferente para "modo IPv6".

### 4. Cliente usando o endereço IPv6 **entre colchetes**

```bash
python -m client.main --server "http://[fe80::1a2b:3c4d:5e6f:7788]:8000"
```

> ⚠️ Os **colchetes `[ ]` são obrigatórios** em qualquer URL com IPv6.
>
> ⚠️ Em httpx (usado pelo cliente), caracteres `%` em URL são tratados como
> escape. **Endereços link-local com identificador de zona (`%wlan0`, `%eth0`,
> `%enp3s0`…) devem ter o `%` escrito como `%25` na URL**:
>
> ```bash
> # endereço: fe80::1a2b:3c4d:5e6f:7788%wlan0  →
> python -m client.main --server "http://[fe80::1a2b:3c4d:5e6f:7788%25wlan0]:8000"
> ```
>
> Se preferir, evite a zona usando um endereço global (ou ULA `fd00::/8`) da rede:
> `python -m client.main --server "http://[2001:db8::10]:8000"` — esses não precisam de `%`.

### 5. Teste antes de abrir o cliente

No **navegador** da máquina cliente (funciona igual, colchetes e `%25`):

```
http://[fe80::1a2b:3c4d:5e6f:7788%25wlan0]:8000/health
```

Ou pelo **terminal** (aqui o `%` é literal, sem `%25`, e a zona é obrigatória
para link-local):

```bash
curl -g "http://[fe80::1a2b:3c4d:5e6f:7788%25wlan0]:8000/health"
# deve responder: {"status":"ok","database":"postgresql"}
```

No Windows (PowerShell), use a zona da interface, ex.: `ping fe80::1a2b:3c4d:5e6f:7788%12`
(o número vem de `ipconfig`, coluna "Índice da interface" da rede usada).

### 6. Interface web e uploads via curl também funcionam em IPv6

```bash
# interface web
http://[fe80::1a2b:3c4d:5e6f:7788%25wlan0]:8000/

# upload de teste
curl -g -F "file=@musica.mp3" -F "processing_type=normalize" \
     "http://[fe80::1a2b:3c4d:5e6f:7788%25wlan0]:8000/api/audios/upload"
```

### Dicas específicas de IPv6

| Situação | Solução |
|----------|---------|
| `ping fe80::…` falha | link-local exige zona: `ping fe80::…%wlan0` (Linux/macOS) ou `ping fe80::…%12` (Windows, nº da interface) |
| Cliente responde *"tempo esgotado ao conectar"* | confirme a zona correta (`%25wlan0` na URL) e o firewall da máquina servidora |
| Docker: o container do banco só escuta IPv4 | o servidor se conecta ao banco em `localhost:5432` pela própria máquina — não é afetado; apenas o acesso do **cliente** precisa de IPv6 |
| Navegador não abre `http://[fe80::…%wlan0]:8000` | alguns navegadores aceitam a forma simples `http://[fe80::…%25wlan0]:8000`; se falhar, use o endereço global (`2001:…`/`fd00:…`) da rede |
| Ambas as máquinas na mesma rede Wi-Fi | os endereços globais aparecem em `ip -6 addr show` (linha `inet6 2xxx:…` ou `fdxx:…`) — prefira-os, não precisam de zona |

> ✅ **Resumo do fluxo com IPv6:** `python -m server` na máquina A +
> `python -m client.main --server "http://[<ipv6-do-servidor>]:8000"` na máquina B.

## 🔌 API (resumo)

| Método | Rota                          | Descrição                                     |
|--------|-------------------------------|-----------------------------------------------|
| POST   | `/api/audios/upload`          | Envia áudio (`file`, `processing_type`, `params_json`) |
| GET    | `/api/audios`                 | Histórico de áudios enviados                  |
| GET    | `/api/audios/{id}`            | Metadados de um áudio                         |
| GET    | `/api/audios/{id}/file?variant=original\|processed` | Download/stream do áudio |
| GET    | `/api/audios/{id}/meta`       | meta.json do registro                         |
| GET    | `/api/audios/trash`           | Conteúdo atual do trash/                      |
| DELETE | `/api/audios/{id}`            | Move para trash/ e remove do banco            |
| GET    | `/api/stats`                  | Estatísticas gerais                           |
| GET    | `/health`                     | Status do servidor e do banco                 |

**Exemplo com curl:**

```bash
# envio com normalização de volume (funciona igual via nome .local ou IPv6 entre colchetes)
curl -F "file=@musica.mp3" -F "processing_type=normalize" \
     http://localhost:8000/api/audios/upload

# envio convertendo para ogg
curl -F "file=@musica.mp3" -F "processing_type=convert" \
     -F 'params_json={"target_ext":"ogg"}' \
     http://localhost:8000/api/audios/upload
```

---

## 🧪 Fluxo de demonstração

1. Subir o banco (`docker compose up -d`) e o servidor (`python -m server`)
2. Abrir o cliente (`python -m client.main --server "http://note-a.local:8000"`)
3. Selecionar um arquivo de áudio e escolher, ex., **Normalização de volume**
4. Enviar — o servidor processa com FFmpeg e registra no banco
5. Reproduzir o áudio **original** e o **processado** no cliente
6. Consultar o **hisenamento AAAA/MM/DD/<uuid>/ → meta.json → waveform
  → htórico** de envios no cliente
7. Conferir os **metadados** no banco: `psql -d audio_db -c "SELECT id, original_name, processing_type, duration_sec FROM audios;"`
8. Mostrar a **organização dos arquivos**: `tree data/storage`
9. Abrir a **interface web** (http://localhost:8000/) e reproduzir os áudios no navegador

---

## 🖼️ Prints

Interface do cliente (PySide6):

![Cliente — conexão, envio e processamento](capturas%20de%20tela/Screenshot_20260918_123408.png)

![Cliente — envio em andamento](capturas%20de%20tela/WhatsApp%20Image%202026-09-18%20at%2012.34.57.jpeg)

![Cliente — histórico e reprodução](capturas%20de%20tela/WhatsApp%20Image%202026-09-18%20at%2012.34.57%20(1).jpeg)

---

## 🛠️ Tecnologias

- **Python 3**
- **FastAPI** — API HTTP do servidor
- **PySide6** — cliente gráfico (Qt 6)
- **FFmpeg** — processamento de áudio
- **PostgreSQL** — armazenamento de metadados
- **SQLAlchemy** — comunicação servidor ↔ banco
- **Pillow** — geração da waveform
- Dois computadores distintos (cliente e servidor) na demonstração

---

## 📄 Licença

MIT — ver arquivo [LICENSE](LICENSE).
