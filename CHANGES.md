# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### 2024-12-20

- ADD: run_connections.py: script that pushes sqlite handled connections from ntrip to mqtt
- ADD: handle_connections.py: script for sqlite interaction
- ADD: ntrip-mqtt-hub.service: systemd unit for run_connections.py script
- ADD: m2t.env: use that environment file to configure (not in repo!)

### 2025-03-23

- CHG: folder structure
- ADD: environment variable for database

### 2025-03-27

- ADD: rtcm parsing, not ready yet

### 2025-10-31

- ADD: scripts for sqlite db handling (init_db.py, add_mountpoint.py)
- FIX: improving connection_hub.py

## Suggestion

- Add Environment File for Variables
