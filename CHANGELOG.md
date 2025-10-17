# Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/)
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **TLS/SSL Support**: Wildcard Let's Encrypt certificate integration from home-lab-actions
  - Certificate generation from environment variables (`TLS_CRT`, `TLS_KEY`)
  - Runtime certificate conversion script (`scripts/generate-certs.sh`)
  - Helper script for certificate formatting (`scripts/convert-certs-to-env.sh`)
  - Nginx SSL/TLS termination configuration
  - Self-signed certificate fallback for development

- **Cloudflare Tunnel Support**: Alternative deployment mode using Cloudflare Zero Trust
  - Cloudflared client integration
  - Auto-detection of deployment mode
  - Mutually exclusive with TLS mode

- **Dual-Mode Architecture**: Support for both TLS and Cloudflare deployments
  - Mode detection via `scripts/startup-config.sh`
  - Dynamic supervisord configuration based on environment
  - Separate docker-compose configurations for each mode

- **Project Organization**: Improved directory structure
  - `scripts/` directory for all bash scripts (5 scripts organized)
  - `docker/compose/` directory for compose configurations
  - Comprehensive README files in each directory
  - `ORGANIZATION.md` documenting the reorganization

- **Deployment Automation**: 
  - `scripts/deploy.sh` with auto-mode detection
  - Multi-file docker-compose setup (base + mode-specific)
  - Simplified compose file naming (`base.yaml`, `local.yaml`, `cloudflare.yaml`)

- **Documentation**:
  - `TLS_SETUP.md` - Comprehensive TLS configuration guide
  - `DEPLOYMENT.md` - Deployment instructions for both modes
  - `scripts/README.md` - Script documentation with usage examples
  - `docker/compose/README.md` - Compose file organization guide
  - `ORGANIZATION.md` - Project reorganization summary

### Changed

- **Docker Configuration**:
  - Updated `docker/Dockerfile.actions` to support both TLS and Cloudflare modes
  - Multi-mode container with cloudflared binary
  - Scripts copied from organized `scripts/` directory
  - `.dockerignore` added to exclude sensitive files and home-lab-actions

- **Compose Files**:
  - Renamed and reorganized to `docker/compose/` directory
  - Simplified naming convention (removed `docker-compose.` prefix)
  - Split into modular files: base, local (TLS), cloudflare
  - Main `docker-compose.yaml` references organized compose files

- **Security Enhancements**:
  - Certificate files properly gitignored (`.crt`, `.key`, `.pem`)
  - Strict file permissions on private keys (600)
  - Environment variable-based certificate management
  - No certificates committed to repository

- **Supervisord Configuration**:
  - Priority-based startup sequence
  - Dynamic service loading based on detected mode
  - Generates mode-specific configuration at runtime

### Removed

- Unused compose files: `docker-compose.yaml.old`, `docker-compose.override.yaml`
- Clutter from project root (scripts and compose files moved to subdirectories)

### Fixed

- Docker build context issues (excluded problematic dependencies via `.dockerignore`)
- Inconsistent file naming across compose configurations

## [0.0.1] - 2025-04-07

### Changed

- Dependency versions updated
