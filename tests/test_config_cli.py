from pathlib import Path

from book_archivar import cli
from book_archivar.config import load_config
from book_archivar.library import read_index


def test_defaults_without_config_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BOOK_ARCHIVAR_CONFIG", raising=False)
    cfg = load_config()
    assert cfg.embedding_model == "bge-m3"
    assert cfg.library_dir.name == "library"


def test_config_file_overrides(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("data_dir: ~/x\nembedding_model: m\nchunk_size: 10\n")
    cfg = load_config(f)
    assert cfg.data_dir == Path("~/x").expanduser()
    assert (cfg.embedding_model, cfg.chunk_size) == ("m", 10)
    assert cfg.chunk_overlap == 200


def test_cli_import_folder(tmp_path, alice_epub, monkeypatch, embeddings, capsys):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(f"data_dir: {tmp_path / 'data'}\n")
    monkeypatch.setattr(cli, "EmbeddingsClient", lambda *a: embeddings)
    assert cli.main(["--config", str(cfg), "import", str(alice_epub.parent)]) == 0
    assert "IMPORTED" in capsys.readouterr().out
    assert len(read_index(tmp_path / "data" / "library" / "index.json")) == 1
