-- Fix credit_transactions type check constraint to allow research_usage and research_refund.
-- The 005_research_credits migration added RPC functions that insert these types,
-- but the check constraint only allowed: purchase, usage, subscription_grant, refund.

ALTER TABLE credit_transactions DROP CONSTRAINT IF EXISTS credit_transactions_type_check;

ALTER TABLE credit_transactions ADD CONSTRAINT credit_transactions_type_check
    CHECK (type = ANY (ARRAY[
        'purchase'::text,
        'usage'::text,
        'subscription_grant'::text,
        'refund'::text,
        'research_usage'::text,
        'research_refund'::text
    ]));
