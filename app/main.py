from fastapi import FastAPI

app = FastAPI(
    title="Digiverso API",
    version="1.0.0"
)

@app.get("/")
def root():
    return {"mensaje": "Digiverso funcionando correctamente"}