import json  # Add this import at the top
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from typing import List, Dict, Optional


# Database connection string
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://bootcamp_user:Tony2011@localhost:5432/ai_bootcamp"
)

def get_connection():
    """Get a database connection."""
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Initialize database tables."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Documents table with vector embedding
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255),
            content TEXT NOT NULL,
            embedding VECTOR(1536),  -- OpenAI embedding dimension
            created_at TIMESTAMP DEFAULT NOW(),
            metadata JSONB DEFAULT '{}'::jsonb

        )
    """)
    
    # Create index for fast similarity search
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS documents_embedding_idx 
        ON documents 
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)
    
    conn.commit()
    cursor.close()
    conn.close()
    print("Database initialized successfully")

def insert_document(title: str, content: str, embedding: List[float], metadata: Optional[Dict] = None) -> int:
    """Insert a document with its embedding."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO documents (title, content, embedding, metadata)
        VALUES (%s, %s, %s::vector, %s)
        RETURNING id
    """, (title, content, embedding, metadata or {}))
    
    doc_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    
    return doc_id

def search_similar(embedding: List[float], limit: int = 5, min_similarity: float = 0.7) -> List[Dict]:
    """
    Search for documents similar to the given embedding.
    Uses cosine similarity: 1 = identical, 0 = completely different.
    """
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("""
        SELECT 
            id,
            title,
            content,
            metadata,
            1 - (embedding <=> %s::vector) as similarity
        FROM documents
        WHERE 1 - (embedding <=> %s::vector) > %s
        ORDER BY similarity DESC
        LIMIT %s
    """, (embedding, embedding, min_similarity, limit))
    
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return [dict(row) for row in results]

import json  # Add this import at the top

def insert_document(title: str, content: str, embedding: List[float], metadata: Optional[Dict] = None) -> int:
    """Insert a document with its embedding."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Convert dict to JSON string for PostgreSQL
    metadata_json = json.dumps(metadata) if metadata else '{}'
    
    cursor.execute("""
        INSERT INTO documents (title, content, embedding, metadata)
        VALUES (%s, %s, %s::vector, %s::jsonb)
        RETURNING id
    """, (title, content, embedding, metadata_json))
    
    doc_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    
    return doc_id

def get_document_count() -> int:
    """Get total number of documents."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM documents")
    count = cursor.fetchone()[0]
    
    cursor.close()
    conn.close()
    
    return count
