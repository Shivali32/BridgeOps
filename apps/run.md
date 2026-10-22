
# Activate
.\apps\api\.venv\Scripts\Activate.ps1


# docker postgres
cd D:\BridgOps
docker compose start postgres

docker compose --profile app up -d --build

docker compose ps
# check if ready and accepting connection
docker exec bridgops-postgres pg_isready -U bridgops -d bridgops_db
# Connect to postgresql in cmd
docker exec -it bridgops-postgres psql -U bridgops -d bridgops_db

docker compose stop postgres

# Migrate check
python -m alembic current


# Starting back and front
cd apps\api
python -m uvicorn app.main:app --reload


cd apps/web
npm.cmd run dev


Terminal	Directory	            Command
Database	D:\BridgOps	            docker compose up -d postgres
Backend	    D:\BridgOps\apps\api	python -m uvicorn app.main:app --reload
Frontend	D:\BridgOps\apps\web	npm.cmd run dev

# Testing Ruff
python -m pytest -v

python -m ruff check app tests
python -m ruff format --check app tests

python -m ruff check app tests --fix
python -m ruff format app tests