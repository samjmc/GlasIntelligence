-- Atomic credit deduction function to prevent race conditions.
-- Usage: SELECT deduct_credit_atomic('user-id-here', 'Simulation run');
-- Returns the new credit balance, or -1 if insufficient credits.

CREATE OR REPLACE FUNCTION deduct_credit_atomic(
    p_user_id UUID,
    p_description TEXT DEFAULT 'simulation'
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_new_credits INTEGER;
BEGIN
    UPDATE profiles
    SET credits = credits - 1
    WHERE id = p_user_id AND credits >= 1
    RETURNING credits INTO v_new_credits;

    IF v_new_credits IS NULL THEN
        RETURN -1;
    END IF;

    INSERT INTO credit_transactions (user_id, amount, type, description)
    VALUES (p_user_id, -1, 'usage', p_description);

    RETURN v_new_credits;
END;
$$;
