# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added - 2024-12-20

- run_connections.py: script that pushes sqlite handled connections from ntrip to mqtt
- handle_connections.py: script for sqlite interaction
- ntrip-mqtt-hub.service: systemd unit for run_connections.py script
- m2t.env: use that environment file to configure (not in repo!)

### Suggestion

- Add Environment File for Variables
