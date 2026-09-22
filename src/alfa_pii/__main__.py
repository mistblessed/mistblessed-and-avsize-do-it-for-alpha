import logging

import uvicorn


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    uvicorn.run("alfa_pii.api.app:create_app", factory=True, host="0.0.0.0", port=8000,
                workers=1, access_log=False, proxy_headers=False, timeout_keep_alive=5)


if __name__ == "__main__":
    main()

