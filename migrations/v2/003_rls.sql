-- Row Level Security: acesso público a leitura, escrita apenas via service_role

ALTER TABLE materias  ENABLE ROW LEVEL SECURITY;
ALTER TABLE fontes    ENABLE ROW LEVEL SECURITY;
ALTER TABLE topicos   ENABLE ROW LEVEL SECURITY;
ALTER TABLE contextos ENABLE ROW LEVEL SECURITY;
ALTER TABLE questoes  ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role full access" ON materias  FOR ALL USING (true);
CREATE POLICY "service_role full access" ON fontes    FOR ALL USING (true);
CREATE POLICY "service_role full access" ON topicos   FOR ALL USING (true);
CREATE POLICY "service_role full access" ON contextos FOR ALL USING (true);
CREATE POLICY "service_role full access" ON questoes  FOR ALL USING (true);

CREATE POLICY "public read" ON materias  FOR SELECT USING (true);
CREATE POLICY "public read" ON fontes    FOR SELECT USING (true);
CREATE POLICY "public read" ON topicos   FOR SELECT USING (true);
CREATE POLICY "public read" ON contextos FOR SELECT USING (true);
CREATE POLICY "public read" ON questoes  FOR SELECT USING (true);
