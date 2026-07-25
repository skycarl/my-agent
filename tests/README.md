# Test Structure

This directory contains all tests for the project, organized by service and test type.

## Structure

```
tests/
├── conftest.py              # Shared pytest fixtures and configuration
├── unit/                    # Unit tests by service
│   ├── app/                 # App service unit tests
│   ├── telegram_bot/        # Telegram bot service unit tests
├── integration/             # Integration tests between services
└── e2e/                    # End-to-end tests
```

## Test Types

### Unit Tests (`tests/unit/`)
- Test individual components in isolation
- Mock external dependencies
- Fast execution
- Located in service-specific directories

### Integration Tests (`tests/integration/`)
- Test interactions between services
- May use real external services (with test credentials)
- Test API endpoints and service communication
- Slower than unit tests

### End-to-End Tests (`tests/e2e/`)
- Test complete user workflows
- Use real services and databases
- Slowest tests, run in CI/CD pipeline
- Test full application behavior

## Running Tests

```bash
# Run all tests
make test

# Run specific test types
make test-unit
make test-integration

# Run tests for specific services
make test-app
make test-telegram

# Run with pytest directly
uv run pytest tests/unit/app/           # App unit tests only
uv run pytest tests/unit/                # All unit tests
uv run pytest tests/integration/        # Integration tests only
```

## Test Conventions

### File Naming
- Test files should be named `test_*.py`
- Test classes should be named `Test*`
- Test functions should be named `test_*`

### Test Selection
Tests are categorized by directory, not by marker — select them by path
(`tests/unit/`, `tests/integration/`, `tests/unit/app/`) or via the `make`
targets above.

### Fixtures
- Shared fixtures are defined in `conftest.py`
- Service-specific fixtures can be defined in service test directories
- Use descriptive fixture names and docstrings

### Mocking
- Mock external dependencies in unit tests
- Use the fixtures provided in `conftest.py` for common mocks
- Keep mocks as close to the test as possible

## Adding New Tests

1. **Unit Tests**: Add to appropriate service directory under `tests/unit/`
2. **Integration Tests**: Add to `tests/integration/`
3. **E2E Tests**: Add to `tests/e2e/`
4. **Shared Fixtures**: Add to `tests/conftest.py`

## Example Test Structure

```python
import pytest
from unittest.mock import Mock, patch

def test_feature_functionality():
    """Test that feature works correctly."""
    # Arrange
    expected_result = "expected"
    
    # Act
    result = feature_function()
    
    # Assert
    assert result == expected_result

def test_service_communication():
    """Test communication between services."""
    # Test service integration
    pass
``` 