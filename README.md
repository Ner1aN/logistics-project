# Система управления грузоперевозками

Учебный веб-проект для диплома по автоматизации деятельности менеджера компании по грузоперевозкам.

## Что реализовано

- авторизация пользователей;
- ведение справочников клиентов, водителей и транспортных средств;
- создание и редактирование заявок на перевозку;
- назначение транспорта и водителя на заявку;
- контроль статусов заявки;
- архивирование заявок;
- базовая отчетность по заявкам и стоимости перевозок;
- административная панель Django.

## Технологии

- Python 3.11+
- Django 6
- SQLite по умолчанию
- PostgreSQL через переменные окружения

## Быстрый запуск

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

После запуска:
- пользователь администратора: `admin`
- пароль: `admin12345`

## PostgreSQL

По умолчанию проект использует SQLite, чтобы его было проще запустить локально. Для переключения на PostgreSQL нужно задать переменные:

```bash
export USE_POSTGRES=1
export POSTGRES_DB=cargo_transport
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=postgres
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
```

## Основные разделы

- `/` — дашборд
- `/clients/` — клиенты
- `/drivers/` — водители
- `/vehicles/` — транспорт
- `/requests/` — заявки
- `/reports/` — отчеты
- `/admin/` — административная панель
