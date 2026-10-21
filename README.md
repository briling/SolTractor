# Setup

- Install either [uv](https://docs.astral.sh/uv/getting-started/installation/) or Conda.
- Install [Ollama](https://ollama.com/download).

Choose one Python environment option below.

## uv

From the project directory, install the locked Python dependencies:

```bash
uv sync --locked
```

uv installs Python 3.13 if needed and creates the environment in `.venv`.
See the [uv project guide](https://docs.astral.sh/uv/guides/projects/).

To activate the environment directly on Linux/macOS:

```bash
source .venv/bin/activate
```

## Conda

From the project directory, create the environment:

```bash
conda env create --name osi --file environment.yml
```

## Ollama

Start Ollama in a separate terminal and leave it running:

```bash
ollama serve
```

Download the model once:

```bash
ollama pull llama3.1
```

# Run

With uv:

```bash
uv run streamlit run app.py
```

With Conda:

```bash
conda activate osi
streamlit run app.py
```

Open <http://localhost:8501/> in your browser.
