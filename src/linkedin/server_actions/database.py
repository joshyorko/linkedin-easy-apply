from sema4ai.actions import Response, action
import os
from pathlib import Path

from ..utils.db import get_connection

@action(is_consequential=False)
def query_database(sql_query: str) -> Response:
    """
    Execute SQL query against the configured database (SQLite/PostgreSQL) and return results. Utility for inspecting database state and debugging enrichment workflow. SELECT statements only.
    
    Args:
        sql_query: SQL query to execute (SELECT statements only for safety)
    
    Returns:
        Response with query results
    """
    try:
        # Safety check - only allow SELECT queries
        query_upper = sql_query.strip().upper()
        if not query_upper.startswith('SELECT'):
            return Response(result={
                "success": False,
                "error": "Only SELECT queries are allowed for safety. Use other actions for INSERT/UPDATE/DELETE.",
                "query": sql_query
            })
        
        print(f"[ACTION] Executing query: {sql_query}")
        
        conn = get_connection()
        cursor = conn.execute(sql_query)
        result = cursor.fetchall()
        
        # Get column names from cursor description
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        
        # Convert to list of dicts for easier reading
        rows = []
        for row in result:
            # Handle both sqlite3.Row and tuple results
            if hasattr(row, 'keys'):
                # sqlite3.Row with row_factory
                row_dict = dict(row)
            else:
                # Regular tuple
                row_dict = dict(zip(columns, row))
            rows.append(row_dict)
        
        print(f"[ACTION] Query returned {len(rows)} rows")
        
        return Response(result={
            "success": True,
            "query": sql_query,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows)
        })
        
    except Exception as e:
        print(f"[ACTION] Error executing query: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return Response(result={
            "success": False,
            "error": str(e),
            "query": sql_query
        })


@action(is_consequential=False)
def get_project_file(file_path: str) -> Response[str]:
    """
    Read contents of a file in the project directory.
    
    Useful for inspecting configuration files, SQL schemas, documentation, and action code
    without leaving the action interface. Great for debugging and understanding the project structure.
    
    Common files to inspect:
    - package.yaml (dependencies and config)
    - sql/schema.sql (database schema)
    - README.md (project documentation)
    - src/linkedin/[module].py (action code)
    - .env.example (environment variable template)
    
    Args:
        file_path: Relative path from project root (e.g., "package.yaml", "sql/schema.sql")
    
    Returns:
        Response with file contents or error if not found
    """
    try:
        # Get project root (go up from src/linkedin/server_actions to project root)
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent.parent
        
        # Construct full path
        full_path = project_root / file_path
        
        # Security: ensure the resolved path is within project_root
        resolved_path = full_path.resolve()
        resolved_root = project_root.resolve()
        
        if not str(resolved_path).startswith(str(resolved_root)):
            return Response(result=f"Error: Access denied. Path must be within project directory.\nAttempted: {file_path}")
        
        if not resolved_path.exists():
            return Response(result=f"Error: File not found: {file_path}\nFull path: {resolved_path}")
        
        if not resolved_path.is_file():
            return Response(result=f"Error: Path is not a file: {file_path}\nUse list_project_files to see directory contents.")
        
        # Read the file
        with open(resolved_path, 'r', encoding='utf-8') as f:
            contents = f.read()
        
        print(f"[ACTION] Read file: {file_path} ({len(contents)} characters)")
        
        # Add helpful context
        file_info = f"File: {file_path}\n"
        file_info += f"Size: {len(contents)} characters\n"
        file_info += f"Lines: {contents.count(chr(10)) + 1}\n"
        file_info += "─" * 60 + "\n\n"
        
        return Response(result=file_info + contents)
        
    except Exception as e:
        print(f"[ACTION] Error reading file: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return Response(result=f"Error reading file: {str(e)}\nPath: {file_path}")


@action(is_consequential=False)
def list_project_files(directory: str = ".") -> Response[str]:
    """
    List files and directories in the project.
    
    Useful for exploring the project structure and finding files to inspect
    with get_project_file(). Shows files and subdirectories with type indicators.
    
    Args:
        directory: Relative path from project root (default: "." for root)
    
    Returns:
        Response with directory listing
    """
    try:
        # Get project root
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent.parent
        
        # Construct full path
        full_path = project_root / directory
        
        # Security: ensure the resolved path is within project_root
        resolved_path = full_path.resolve()
        resolved_root = project_root.resolve()
        
        if not str(resolved_path).startswith(str(resolved_root)):
            return Response(result=f"Error: Access denied. Path must be within project directory.")
        
        if not resolved_path.exists():
            return Response(result=f"Error: Directory not found: {directory}")
        
        if not resolved_path.is_dir():
            return Response(result=f"Error: Path is not a directory: {directory}\nUse get_project_file to read files.")
        
        # List contents
        items = []
        
        # Get all items and sort (directories first, then files)
        all_items = list(resolved_path.iterdir())
        dirs = sorted([item for item in all_items if item.is_dir()], key=lambda x: x.name.lower())
        files = sorted([item for item in all_items if item.is_file()], key=lambda x: x.name.lower())
        
        for item in dirs:
            # Skip common uninteresting directories
            if item.name in ['__pycache__', '.git', 'node_modules', '.venv', 'venv']:
                continue
            items.append(f"📁 {item.name}/")
        
        for item in files:
            # Add emoji indicators for common file types
            if item.suffix in ['.py']:
                icon = '🐍'
            elif item.suffix in ['.yaml', '.yml']:
                icon = '⚙️'
            elif item.suffix in ['.sql']:
                icon = '🗄️'
            elif item.suffix in ['.md']:
                icon = '📝'
            elif item.suffix in ['.json']:
                icon = '📋'
            elif item.suffix in ['.txt', '.log']:
                icon = '📄'
            else:
                icon = '📄'
            
            items.append(f"{icon} {item.name}")
        
        if not items:
            return Response(result=f"Directory is empty: {directory}")
        
        result = f"Contents of: {directory}\n"
        result += f"Location: {resolved_path}\n"
        result += "─" * 60 + "\n\n"
        result += "\n".join(items)
        result += f"\n\n─" * 60 + "\n"
        result += f"Total: {len(dirs)} directories, {len(files)} files"
        
        print(f"[ACTION] Listed directory: {directory} ({len(items)} items)")
        
        return Response(result=result)
        
    except Exception as e:
        print(f"[ACTION] Error listing directory: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return Response(result=f"Error listing directory: {str(e)}\nPath: {directory}")
