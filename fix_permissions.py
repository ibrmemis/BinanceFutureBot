import os
import sys
from sqlalchemy import create_engine, text

# Load env
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL not found in .env")
    DATABASE_URL = "sqlite:///./trading_bot.db"

def fix_permissions():
    print(f"🔌 Connecting to: {DATABASE_URL}")
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.connect() as conn:
            print("🔍 Checking current user...")
            result = conn.execute(text("SELECT current_user"))
            current_user = result.scalar()
            print(f"👤 Current User: {current_user}")
            
            print("\n🔍 Checking sequence owner...")
            try:
                result = conn.execute(text("""
                    SELECT c.relname, r.rolname 
                    FROM pg_class c 
                    JOIN pg_roles r ON r.oid = c.relowner 
                    WHERE c.relname = 'position_history_id_seq';
                """))
                row = result.fetchone()
                if row:
                    print(f"🔐 Sequence '{row[0]}' is owned by: '{row[1]}'")
                    owner = row[1]
                else:
                    print("⚠️ Sequence 'position_history_id_seq' not found! (Maybe it's named differently?)")
                    owner = None
            except Exception as e:
                print(f"⚠️ Could not check owner: {e}")
                owner = None

            print("\n🛠️ Attempting fixes...")
            
            # Fix 1: Grant Usage (Simplest fix for 'InsufficientPrivilege')
            print("1️⃣ Attempting: GRANT USAGE on sequence...")
            try:
                conn.execute(text("GRANT USAGE, SELECT ON SEQUENCE position_history_id_seq TO postgres;"))
                conn.commit()
                print("✅ Fix 1 (GRANT) executed successfully!")
            except Exception as e:
                print(f"❌ Fix 1 failed: {e}")
                conn.rollback()

            # Fix 2: Change Owner (If needed and possible)
            if owner and owner != "postgres":
                print(f"\n2️⃣ Attempting: Change owner from {owner} to postgres...")
                try:
                    conn.execute(text("ALTER SEQUENCE position_history_id_seq OWNER TO postgres;"))
                    conn.commit()
                    print("✅ Fix 2 (ALTER OWNER) executed successfully!")
                except Exception as e:
                    print(f"❌ Fix 2 failed: {e}")
                    conn.rollback()
            
            # Fix 3: Grant All on Schema (Broad fix)
            print("\n3️⃣ Attempting: GRANT ALL on public schema...")
            try:
                conn.execute(text("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;"))
                conn.commit()
                print("✅ Fix 3 (GRANT ALL) executed successfully!")
            except Exception as e:
                print(f"❌ Fix 3 failed: {e}")
                conn.rollback()
                
            print("\n🏁 Done.")

    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    fix_permissions()
