import tomllib
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

with open("../config.toml", "rb") as f:
    config = tomllib.load(f)

config["app"]["data_dir"] = Path(config["app"]["data_dir"])