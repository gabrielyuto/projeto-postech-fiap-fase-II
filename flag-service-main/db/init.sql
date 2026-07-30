CREATE TABLE IF NOT EXISTS flags (
    id SERIAL PRIMARY KEY,

    -- 'name' é a chave de negócio única (ex: 'enable-new-checkout')
    name VARCHAR(100) UNIQUE NOT NULL, 
    
    description TEXT,
    
    -- Este é o 'kill switch' global. Se for false, a flag está desativada para todos.
    is_enabled BOOLEAN NOT NULL DEFAULT false,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Opcional, mas boa prática: Trigger para atualizar 'updated_at' automaticamente
CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Remove o trigger se já existir, para evitar erro na recriação
DROP TRIGGER IF EXISTS set_timestamp ON flags;

CREATE TRIGGER set_timestamp
BEFORE UPDATE ON flags
FOR EACH ROW
EXECUTE PROCEDURE trigger_set_timestamp();