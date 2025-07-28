from fastapi import FastAPI
import uvicorn

app = FastAPI()


@app.get("/")
def root():
    return {"status": "ok", "bot": "blizkie_igry"}


if __name__ == "__main__":
    uvicorn.run("bot.utils.healthcheck_http:app", host="0.0.0.0", port=8000)
