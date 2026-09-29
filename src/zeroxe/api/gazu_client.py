import gazu
from zeroxe import config

gazu_client = gazu
try:
    gazu_client.set_host(config.KITSU_API_URL)
    print(gazu_client.client.get_api_version())
except Exception as e:
    raise e