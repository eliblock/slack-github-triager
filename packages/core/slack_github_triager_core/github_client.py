import logging
from dataclasses import dataclass
from datetime import datetime, time

import jwt
import requests

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GithubAppConfig:
    app_id: str
    private_key: str
    target_org: str


class GithubRequestClient:
    def __init__(
        self,
        app_id: str,
        private_key: str,
        target_org: str,
    ):
        self.session = requests.session()
        self.session.headers["Accept"] = "application/vnd.github+json"
        self.session.headers["Authorization"] = (
            f"Bearer {self._get_github_installation_token(app_id, private_key, target_org)}"
        )

    def _get_github_installation_token(
        self, app_id: str, private_key: str, target_org: str
    ) -> str:
        # get jwt token
        now = int(datetime.now().timestamp())
        token = jwt.encode(
            {"iat": now - 60, "exp": now + (8 * 60), "iss": app_id},
            key=private_key,
            algorithm="RS256",
        )

        # get installation for org
        response = self.session.get(
            "https://api.github.com/app/installations",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
            },
        )
        response.raise_for_status()
        installations = response.json()

        installation_id = None
        for installation in installations:
            if installation.get("account", {}).get("login") == target_org:
                installation_id = installation["id"]
                break

        if installation_id is None:
            raise RuntimeError(f"No installation found for organization '{target_org}'")

        # get installation token
        response = self.session.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
            },
        )
        response.raise_for_status()
        return response.json()["token"]

    def _make_github_request(
        self, method: str, path: str, **kwargs
    ) -> requests.Response:
        assert path and path[0] == "/"

        url = f"https://api.github.com{path}"

        while True:
            response = self.session.request(method, url, **kwargs)
            try:
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get("Retry-After", 1))
                    logger.warning(
                        f"Rate limit hit. Retrying after {retry_after} seconds..."
                    )
                    time.sleep(retry_after)
                else:
                    raise

    def get(self, path: str, **kwargs) -> dict:
        return self._make_github_request("GET", path, **kwargs).json()
