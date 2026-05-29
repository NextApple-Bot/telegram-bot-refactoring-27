-- Партиционирование таблицы daily_payments по месяцам
-- Внимание: выполнять после создания основной таблицы!

-- Создаём партиционированную таблицу-родитель
CREATE TABLE daily_payments_partitioned (
    LIKE daily_payments INCLUDING DEFAULTS INCLUDING CONSTRAINTS
) PARTITION BY RANGE (created_at);

-- Переносим данные (если есть)
INSERT INTO daily_payments_partitioned SELECT * FROM daily_payments;

-- Создаём партиции на ближайшие месяцы (пример)
CREATE TABLE daily_payments_2026_01 PARTITION OF daily_payments_partitioned
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE daily_payments_2026_02 PARTITION OF daily_payments_partitioned
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
-- Добавлять по мере необходимости

-- Переименовываем таблицы (осторожно!)
-- BEGIN;
-- ALTER TABLE daily_payments RENAME TO daily_payments_old;
-- ALTER TABLE daily_payments_partitioned RENAME TO daily_payments;
-- COMMIT;
