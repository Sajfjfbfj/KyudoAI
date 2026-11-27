-- YUMIQA（弓道AI）Supabase 初期セットアップSQL
-- Supabase 管理画面の「SQL Editor」に貼り付けて「Run」を押してください。

-- 1. ユーザーアカウントテーブル
CREATE TABLE IF NOT EXISTS public.yumiqa_users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    display_name TEXT DEFAULT '',
    created_at TEXT DEFAULT '',
    restored BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. ユーザー別データテーブル（会話履歴・メモリ・設定・ピン留め等）
CREATE TABLE IF NOT EXISTS public.yumiqa_user_data (
    data_key TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    category TEXT NOT NULL,
    item_id TEXT DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TEXT DEFAULT ''
);

-- 検索高速化用インデックス
CREATE INDEX IF NOT EXISTS idx_yumiqa_user_data_user_cat
    ON public.yumiqa_user_data (username, category);

-- RLS（Row Level Security）について：
-- Streamlit サーバー側で service_role key（または anon key）を使ってアクセスするため、
-- ベータ版では RLS を無効のままにするか、全許可ポリシーを設定します。
ALTER TABLE public.yumiqa_users DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.yumiqa_user_data DISABLE ROW LEVEL SECURITY;
