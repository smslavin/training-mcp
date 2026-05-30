from app import mcp
import routers  # pyright: ignore[reportUnusedImport] — side-effect import: registers tools with mcp

if __name__ == "__main__":
    mcp.run()
