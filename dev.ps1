Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$PSScriptRoot\venv\Scripts\Activate.ps1'; cd '$PSScriptRoot\backend'; python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\frontend'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "ngrok http --domain=counterproductive-unphenomenally-amberly.ngrok-free.dev 5173"
