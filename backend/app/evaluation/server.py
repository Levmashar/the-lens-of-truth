"""Normal development API, intended to run inside the persistent call-budget wrapper."""

import uvicorn


def main() -> None:
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, workers=1)


if __name__ == "__main__":
    main()
