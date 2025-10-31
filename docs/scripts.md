# Scripts Documentation

This document describes the utility scripts found in the `scripts/` directory of the TR-M2T project.

## 1. `init_db.py`
Initializes the SQLite database with the required `mountpoints` table.

**Usage:**
```
python3 scripts/init_db.py
```

---

## 2. `add_mountpoint.py`
Adds a new mountpoint entry to the database.

**Usage:**
```
python3 scripts/add_mountpoint.py --name "mount1" --connection "ntrip://user:pass@host:port/mount" --active 1
```
- `--name`: Name of the mountpoint (required)
- `--connection`: Connection string (required)
- `--active`: 1 for active, 0 for inactive (default: 1)

---

## 3. `set_mountpoint_active.py`
Enables or disables a mountpoint by its ID.

**Usage:**
```
python3 scripts/set_mountpoint_active.py --id 1 --active 1   # Enable
python3 scripts/set_mountpoint_active.py --id 1 --active 0   # Disable
```
- `--id`: Mountpoint ID (required)
- `--active`: 1 to enable, 0 to disable (required)

---

## 4. `parallel_add_mountpoints.py`
(Adds multiple mountpoints in parallel using multiple loaders. If present.)

**Usage:**
```
python3 scripts/parallel_add_mountpoints.py --file var/mountpoints.txt --loaders 4
```
- `--file`: Path to file with mountpoints (required)
- `--loaders`: Number of parallel loaders (default: 4)

---

For more details, see the script source code or run with `--help`.
