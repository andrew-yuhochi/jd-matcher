import os
from pathlib import Path

from dotenv import load_dotenv

from jd_matcher.errors import ConfigError


def get_openai_key() -> str:
    """Return the OpenAI API key from the environment.

    Searches for .env starting at the current working directory so tests can
    chdir to a tmp_path with a fixture .env.  Shell-exported vars take
    precedence over .env (standard 12-factor convention: .env fills defaults
    for unset vars only, never overwrites operator-set values).
    Raises ConfigError with an actionable message when the key is absent.
    """
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ConfigError(
            "OPENAI_API_KEY is not set. Add it to your .env file "
            "(see docs/poc/SETUP.md §4 'OpenAI API key setup' for how to obtain one)."
        )
    return key
