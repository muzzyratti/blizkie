from fastapi import FastAPI
import uvicorn

app = FastAPI()


@app.get("/")
def root():
    return {"status": "ok", "bot": "blizkie_igry"}


if __name__ == "__main__":
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__ + "/../../..")))
    import uvicorn
    uvicorn.run("bot.utils.healthcheck_http:app", host="0.0.0.0", port=8000)