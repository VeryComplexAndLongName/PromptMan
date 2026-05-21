-- Create table for caching popular requests
CREATE TABLE cache_requests (
    id SERIAL PRIMARY KEY,
    request_key TEXT NOT NULL UNIQUE, -- Unique key for the request (e.g., URL + params)
    payload JSONB,                   -- Optional payload for the request
    lru BIGINT DEFAULT 0 NOT NULL    -- Popularity counter (incremented on each save)
);