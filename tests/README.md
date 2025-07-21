# Test Structure

This directory contains all tests for the project, organized by service and test type.

## Structure

```
tests/
├── conftest.py              # Shared pytest fixtures and configuration
├── unit/                    # Unit tests by service
│   ├── app/                 # App service unit tests
│   ├── telegram_bot/        # Telegram bot service unit tests
│   └── my_mcp/             # MCP service unit tests
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
make test-e2e

# Run tests for specific services
make test-app
make test-telegram
make test-mcp

# Run with pytest directly
uv run pytest tests/unit/app/           # App unit tests only
uv run pytest tests/integration/        # Integration tests only
uv run pytest -m "unit"                 # All unit tests
uv run pytest -m "integration"          # All integration tests
```

## Test Conventions

### File Naming
- Test files should be named `test_*.py`
- Test classes should be named `Test*`
- Test functions should be named `test_*`

### Markers
Use pytest markers to categorize tests:
- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.e2e` - End-to-end tests
- `@pytest.mark.slow` - Tests that take longer to run
- `@pytest.mark.app` - App service tests
- `@pytest.mark.telegram` - Telegram bot tests
- `@pytest.mark.mcp` - MCP service tests

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

@pytest.mark.unit
@pytest.mark.app
def test_feature_functionality():
    """Test that feature works correctly."""
    # Arrange
    expected_result = "expected"
    
    # Act
    result = feature_function()
    
    # Assert
    assert result == expected_result

@pytest.mark.integration
def test_service_communication():
    """Test communication between services."""
    # Test service integration
    pass
``` 