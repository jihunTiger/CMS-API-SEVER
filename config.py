from pydantic import BaseSettings


class Settings(BaseSettings):
    DEFAULT_VAR="some default string value" # default value if env variable does not exist
    MONGODB_URL: str


# specify .env file location as Config attribute
    class Config:
        env_file = ".env"