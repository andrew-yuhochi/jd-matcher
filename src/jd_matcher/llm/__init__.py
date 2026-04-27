import os
from pathlib import Path

from dotenv import load_dotenv

from jd_matcher.errors import ConfigError


def get_openai_key() -> str:
    """Return the OpenAI API key from the environment.

    Searches for .env starting at the current working directory so tests can
    chdir to a tmp_path with a fixture .env.  override=True ensures a fresh
    read even if load_dotenv was called previously in the same process.
    Raises ConfigError with an actionable message when the key is absent.
    """
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=True)
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ConfigError(
            "OPENAI_API_KEY is not set. Add it to your .env file "
            "(see docs/poc/SETUP.md §4 'OpenAI API key setup' for how to obtain one)."
        )
    return key
