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

## ▶️ Execução do servidor

```bash
source .venv/bin/activate
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

- **Interface web:** http://localhost:8000/
- **Documentação interativa (Swagger):** http://localhost:8000/docs

## ▶️ Execução do cliente

Em **outra máquina** (ou na mesma), apontando para o IP do servidor:

```bash
source .venv/bin/activate
python -m client.main --server http://192.168.0.42:8000   # IP do servidor
# sem --server, conecta em http://127.0.0.1:8000
```

---

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
# envio com normalização de volume
curl -F "file=@musica.mp3" -F "processing_type=normalize" \
     http://localhost:8000/api/audios/upload

# envio convertendo para ogg
curl -F "file=@musica.mp3" -F "processing_type=convert" \
     -F 'params_json={"target_ext":"ogg"}' \
     http://localhost:8000/api/audios/upload
```

---

## 🧪 Fluxo de demonstração

1. Subir o banco (`docker compose up -d`) e o servidor (`uvicorn server.main:app`)
2. Abrir o cliente (`python -m client.main --server http://IP:8000`)
3. Selecionar um arquivo de áudio e escolher, ex., **Normalização de volume**
4. Enviar — o servidor processa com FFmpeg e registra no banco
5. Reproduzir o áudio **original** e o **processado** no cliente
6. Consultar o **histórico** de envios no cliente
7. Conferir os **metadados** no banco: `psql -d audio_db -c "SELECT id, original_name, processing_type, duration_sec FROM audios;"`
8. Mostrar a **organização dos arquivos**: `tree data/storage`
9. Abrir a **interface web** (http://localhost:8000/) e reproduzir os áudios no navegador

---

## 🖼️ Prints

> Adicione aqui os screenshots da interface do cliente, da interface web e da
> organização dos arquivos (`tree data/storage`) após executar o sistema.

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
