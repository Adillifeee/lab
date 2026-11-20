# Project instructions

- This repository implements a city delivery management system using Python, FastAPI, SQLModel, SQLite, and Streamlit.
- Keep API routes in `app/routers/`, database models in `app/database/models.py`, and the Streamlit interface in `app/frontend/`.
- Preserve the existing role-based access rules, delivery status transitions, and price calculation behavior when changing business logic.
- Use the existing SQLModel models and dependencies; avoid adding dependencies unless they are needed.
- Run the focused tests with `.venv\Scripts\python.exe -m pytest` after changing application behavior.
- Do not commit credentials, `.env` files, local databases, or the `.venv` directory.
