-- Add research_credits column and atomic deduction function.
-- Run this migration in Supabase SQL Editor before deploying the code.

-- 1. Add column
ALTER TABLE profiles
ADD COLUMN IF NOT EXISTS research_credits INTEGER NOT NULL DEFAULT 0;

-- 2. Atomic deduction function (mirrors deduct_credit_atomic)
CREATE OR REPLACE FUNCTION deduct_research_credit_atomic(
    p_user_id UUID,
    p_description TEXT DEFAULT 'deep_research'
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_new_credits INTEGER;
BEGIN
    UPDATE profiles
    SET research_credits = research_credits - 1
    WHERE id = p_user_id AND research_credits >= 1
    RETURNING research_credits INTO v_new_credits;

    IF v_new_credits IS NULL THEN
        RETURN -1;
    END IF;

    INSERT INTO credit_transactions (user_id, amount, type, description)
    VALUES (p_user_id, -1, 'research_usage', p_description);

    RETURN v_new_credits;
END;
$$;

-- 3. Refund helper (for failed research)
CREATE OR REPLACE FUNCTION refund_research_credit(
    p_user_id UUID,
    p_description TEXT DEFAULT 'research_refund'
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_new_credits INTEGER;
BEGIN
    UPDATE profiles
    SET research_credits = research_credits + 1
    WHERE id = p_user_id
    RETURNING research_credits INTO v_new_credits;

    INSERT INTO credit_transactions (user_id, amount, type, description)
    VALUES (p_user_id, 1, 'research_refund', p_description);

    RETURN COALESCE(v_new_credits, 0);
END;
$$;

-- 4. Backfill existing paid users
UPDATE profiles SET research_credits = 3 WHERE plan = 'pro';
UPDATE profiles SET research_credits = 13 WHERE plan = 'business';
UPDATE profiles SET research_credits = 33 WHERE plan = 'enterprise';
