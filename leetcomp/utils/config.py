import tomllib
from pathlib import Path

config_path = Path(__file__).parent.parent.parent / "config.toml"
with open(config_path, "rb") as f:
    config = tomllib.load(f)

config["app"]["data_dir"] = Path(config["app"]["data_dir"])
