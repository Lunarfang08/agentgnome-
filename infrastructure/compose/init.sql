CREATE ROLE agentgenome LOGIN PASSWORD 'local-development' NOSUPERUSER NOBYPASSRLS;
CREATE DATABASE agentgenome OWNER agentgenome;
CREATE ROLE temporal LOGIN PASSWORD 'local-temporal' NOSUPERUSER;
CREATE DATABASE temporal OWNER temporal;
CREATE DATABASE temporal_visibility OWNER temporal;
\connect agentgenome
CREATE EXTENSION IF NOT EXISTS vector;
