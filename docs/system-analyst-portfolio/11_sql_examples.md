# 11. SQL-примеры

Примеры ниже ориентированы на SQLite и таблицы Django-проекта.

## 1. Список заявок с клиентом и статусом

```sql
SELECT
    r.id,
    c.name AS client_name,
    s.name AS status_name,
    r.transportation_date,
    r.cost
FROM logistics_transportationrequest r
JOIN logistics_client c ON c.id = r.client_id
JOIN logistics_requeststatus s ON s.id = r.status_id
ORDER BY r.transportation_date DESC;
```

## 2. Количество заявок по статусам

```sql
SELECT
    s.name AS status_name,
    COUNT(r.id) AS request_count
FROM logistics_requeststatus s
LEFT JOIN logistics_transportationrequest r ON r.status_id = s.id
GROUP BY s.id, s.name
ORDER BY s."order";
```

## 3. Сумма заявок по клиентам

```sql
SELECT
    c.name AS client_name,
    COUNT(r.id) AS request_count,
    COALESCE(SUM(r.cost), 0) AS total_cost
FROM logistics_client c
LEFT JOIN logistics_transportationrequest r ON r.client_id = c.id
GROUP BY c.id, c.name
ORDER BY total_cost DESC;
```

## 4. Активные заявки

```sql
SELECT
    r.id,
    c.name AS client_name,
    s.code AS status_code,
    r.transportation_date
FROM logistics_transportationrequest r
JOIN logistics_client c ON c.id = r.client_id
JOIN logistics_requeststatus s ON s.id = r.status_id
WHERE r.archived = 0
  AND s.code NOT IN ('completed', 'cancelled')
ORDER BY r.transportation_date;
```

## 5. Архивные заявки

```sql
SELECT
    r.id,
    c.name AS client_name,
    s.name AS status_name,
    r.updated_at
FROM logistics_transportationrequest r
JOIN logistics_client c ON c.id = r.client_id
JOIN logistics_requeststatus s ON s.id = r.status_id
WHERE r.archived = 1
ORDER BY r.updated_at DESC;
```

## 6. История статусов по заявке

```sql
SELECT
    h.request_id,
    s.name AS status_name,
    h.changed_at,
    u.username AS changed_by
FROM logistics_requeststatushistory h
JOIN logistics_requeststatus s ON s.id = h.status_id
LEFT JOIN auth_user u ON u.id = h.changed_by_id
WHERE h.request_id = 1
ORDER BY h.changed_at DESC;
```

## 7. Назначенные ТС по заявкам

```sql
SELECT
    r.id AS request_id,
    v.registration_number,
    d.full_name AS driver_name,
    t.trip_count,
    t.distance_parking_to_loading_km,
    t.distance_loading_to_customer_km,
    t.distance_customer_to_loading_km
FROM logistics_transportation t
JOIN logistics_transportationrequest r ON r.id = t.request_id
JOIN logistics_vehicle v ON v.id = t.vehicle_id
JOIN logistics_driver d ON d.id = t.driver_id
ORDER BY r.id, t.assigned_at;
```

## 8. Заявки с несколькими ТС

```sql
SELECT
    r.id AS request_id,
    c.name AS client_name,
    COUNT(t.id) AS vehicle_assignments
FROM logistics_transportationrequest r
JOIN logistics_client c ON c.id = r.client_id
JOIN logistics_transportation t ON t.request_id = r.id
GROUP BY r.id, c.name
HAVING COUNT(t.id) > 1
ORDER BY vehicle_assignments DESC;
```

## 9. Загрузка водителей по выполненным перевозкам

```sql
SELECT
    d.full_name,
    COUNT(t.id) AS transportation_count,
    COALESCE(SUM(t.trip_count), 0) AS trip_count
FROM logistics_transportation t
JOIN logistics_driver d ON d.id = t.driver_id
JOIN logistics_transportationrequest r ON r.id = t.request_id
JOIN logistics_requeststatus s ON s.id = r.status_id
WHERE s.code = 'completed'
GROUP BY d.id, d.full_name
ORDER BY trip_count DESC;
```

## 10. Расчет километража по перевозкам

```sql
SELECT
    t.id,
    t.request_id,
    v.registration_number,
    t.trip_count,
    (
        t.distance_parking_to_loading_km
        + t.distance_loading_to_customer_km * t.trip_count
        + t.distance_customer_to_loading_km * (t.trip_count - 1)
    ) AS total_distance_km
FROM logistics_transportation t
JOIN logistics_vehicle v ON v.id = t.vehicle_id
ORDER BY total_distance_km DESC;
```

## 11. Просроченные активные заявки

```sql
SELECT
    r.id,
    c.name AS client_name,
    r.transportation_date,
    s.name AS status_name
FROM logistics_transportationrequest r
JOIN logistics_client c ON c.id = r.client_id
JOIN logistics_requeststatus s ON s.id = r.status_id
WHERE r.transportation_date < DATE('now')
  AND s.code NOT IN ('completed', 'cancelled')
ORDER BY r.transportation_date;
```

## 12. Средняя стоимость заявки

```sql
SELECT
    ROUND(AVG(cost), 2) AS average_request_cost
FROM logistics_transportationrequest;
```

## 13. Свободные водители

```sql
SELECT
    id,
    full_name,
    phone
FROM logistics_driver
WHERE is_available = 1
ORDER BY full_name;
```

## 14. Свободный транспорт

```sql
SELECT
    id,
    registration_number,
    brand,
    model,
    capacity_tons
FROM logistics_vehicle
WHERE is_available = 1
ORDER BY registration_number;
```

## 15. Выручка по типам груза

```sql
SELECT
    cargo_type,
    COUNT(id) AS request_count,
    COALESCE(SUM(cost), 0) AS total_cost
FROM logistics_transportationrequest
GROUP BY cargo_type
ORDER BY total_cost DESC;
```
