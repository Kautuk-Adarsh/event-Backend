from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
load_dotenv()
from app.api.endpoints import router # Import the endpoints we wrote above




app = FastAPI(title="Event AI Backend")

# Enable CORS so your Frontend (localhost:3000) can talk to this Backend (localhost:8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach the routes from endpoints.py
app.include_router(router)

@app.get("/")
def health_check():
    return {"status": "running", "message": "Event AI Backend is online"}