-- 1. Eskilarni o'chirish
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS users;
DROP TYPE IF EXISTS userrole;

-- 2. ENUM yaratish
CREATE TYPE userrole AS ENUM ('admin', 'director', 'employee', 'super_employee');

-- 3. Foydalanuvchilar jadvali
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    username VARCHAR(50),
    role userrole DEFAULT 'employee',
    personal_sheet_id VARCHAR(100),
    worksheet_name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Vazifalar jadvali (feedbacks qo'shildi ✅)
CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    assigner_id BIGINT,
    task_name TEXT NOT NULL,
    deadline VARCHAR(50),
    status VARCHAR(50) DEFAULT 'Yangi',
    row_index INTEGER NOT NULL,
    feedbacks JSONB DEFAULT '{}'::jsonb, -- Feedbacklarni saqlash uchun ✅
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Indekslar
CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_tasks_user_id ON tasks(user_id);