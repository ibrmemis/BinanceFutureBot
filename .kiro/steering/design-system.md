---
inclusion: always
---

# Design System Rules for OKX Trading Bot

This document provides comprehensive design system rules for integrating Figma designs with the OKX Trading Bot codebase using the Figma MCP integration.

## Project Overview

**Framework**: Streamlit (Python web framework)
**Styling**: Custom CSS with Streamlit theming
**Language**: Python
**UI Architecture**: Component-based Streamlit pages with custom CSS styling

## Design System Structure

### 1. Token Definitions

**Location**: `.streamlit/config.toml` and `.streamlit/style.css`

**Color Tokens**:
```toml
[theme]
primaryColor = "#FF6B6B"           # Primary action color (red-orange)
backgroundColor = "#0E1117"        # Dark background
secondaryBackgroundColor = "#262730" # Secondary dark background
textColor = "#FAFAFA"             # Light text color
```

**Typography Scale**:
```css
h1: 1.5rem (reduced from default)
h2: 1.2rem (reduced from default)  
h3: 1rem (reduced from default)
body: 0.85rem (compact UI)
caption: 0.75rem (small text)
```

**Spacing Tokens**:
```css
margin-top: 0.2rem - 0.5rem (compact spacing)
margin-bottom: 0.2rem - 0.5rem (compact spacing)
padding: 0.3rem - 0.8rem (button/input padding)
gap: 0.3rem - 0.5rem (element spacing)
```

### 2. Component Library

**Location**: Streamlit built-in components with custom CSS overrides

**Core Components**:
- `st.button()` - Action buttons with custom compact styling
- `st.selectbox()` - Dropdown selections for trading pairs, directions
- `st.number_input()` - Numeric inputs for trading values (leverage, amounts)
- `st.columns()` - Layout system for responsive design
- `st.tabs()` - Navigation between different trading sections
- `st.dataframe()` - Data display for positions, orders, history
- `st.metric()` - Key performance indicators (PnL, balance, etc.)
- `st.expander()` - Collapsible sections for detailed information

**Custom Component Patterns**:
```python
# Status indicators with emojis
STATUS_RUNNING = "✅ Bot Çalışıyor"
STATUS_STOPPED = "⏸️ Bot Durdu"
DIRECTION_LONG = "🟢 LONG"
DIRECTION_SHORT = "🔴 SHORT"

# Button patterns
st.button("🚀 Pozisyon Aç", type="primary", use_container_width=True)
st.button("🔄 Yenile", width="stretch")
```

### 3. Frameworks & Libraries

**UI Framework**: Streamlit 1.51.0+
**Styling**: Custom CSS with Streamlit theming system
**Data Display**: Pandas DataFrames with Streamlit integration
**Icons**: Emoji-based icon system (🚀, 📊, ⚙️, etc.)
**Build System**: Python with requirements.txt dependency management

### 4. Asset Management

**Location**: `attached_assets/` directory (currently empty)
**Strategy**: Minimal asset usage, primarily emoji-based icons
**Optimization**: No specific CDN, relies on Streamlit's built-in asset handling

### 5. Icon System

**Approach**: Emoji-based icon system for consistency and simplicity
**Common Icons**:
- 🚀 - Action/Launch (opening positions)
- 📊 - Data/Analytics (positions, charts)
- ⚙️ - Settings/Configuration
- 🔄 - Refresh/Reload
- 💾 - Save operations
- 🗑️ - Delete operations
- ✅ - Success states
- ❌ - Error states
- 🟢 - Long positions/positive values
- 🔴 - Short positions/negative values

### 6. Styling Approach

**Method**: Custom CSS with Streamlit component targeting
**Global Styles**: Defined in `.streamlit/style.css`
**Responsive Design**: Streamlit's built-in column system

**Key CSS Patterns**:
```css
/* Compact UI - reduced spacing throughout */
.element-container { margin-bottom: 0.3rem !important; }

/* Component-specific styling */
.stButton button { padding: 0.3rem 0.8rem !important; }
.stNumberInput input { padding: 0.3rem !important; }

/* Data display optimization */
.dataframe { font-size: 0.8rem !important; }
```

### 7. Project Structure

```
├── app.py                 # Main Streamlit application
├── constants.py           # UI constants and enums
├── .streamlit/
│   ├── config.toml       # Theme configuration
│   └── style.css         # Custom CSS overrides
├── database.py           # Data models
├── okx_client.py         # API integration
├── trading_strategy.py   # Business logic
└── background_scheduler.py # Background processes
```

## Figma Integration Guidelines

### Design-to-Code Mapping

**When converting Figma designs to Streamlit:**

1. **Replace Tailwind/CSS with Streamlit Components**:
   - `<div>` → `st.container()` or `st.columns()`
   - `<button>` → `st.button()`
   - `<input>` → `st.number_input()`, `st.text_input()`, `st.selectbox()`
   - `<table>` → `st.dataframe()`

2. **Color System Mapping**:
   - Primary actions → `type="primary"` (uses primaryColor from theme)
   - Secondary actions → `type="secondary"`
   - Success states → `st.success()` with ✅ emoji
   - Error states → `st.error()` with ❌ emoji
   - Warning states → `st.warning()` with ⚠️ emoji

3. **Typography Mapping**:
   - H1 → `st.markdown("# Title")` (will be styled to 1.5rem)
   - H2 → `st.markdown("## Subtitle")` (will be styled to 1.2rem)
   - H3 → `st.markdown("### Section")` (will be styled to 1rem)
   - Body → Default Streamlit text
   - Caption → `st.caption("Small text")`

4. **Layout System**:
   - Use `st.columns()` for horizontal layouts
   - Use `st.container(border=True)` for grouped content
   - Use `st.tabs()` for navigation sections
   - Use `st.expander()` for collapsible content

5. **Data Display**:
   - Tables → `st.dataframe()` with custom column configuration
   - Metrics → `st.metric()` with delta indicators
   - Progress → `st.progress()` or custom progress columns

### Component Reuse Patterns

**Existing Components to Reuse**:
- Trading form layouts (3-column input groups)
- Status indicators with emoji prefixes
- Action button groups with consistent spacing
- Data tables with custom column configurations
- Tab-based navigation structure

### Responsive Design

**Streamlit's Column System**:
```python
# Responsive layout patterns
col1, col2, col3 = st.columns(3)  # Equal width
col1, col2 = st.columns([2, 1])   # 2:1 ratio
col1, col2, col3 = st.columns([1, 2, 1])  # Center emphasis
```

### State Management

**Streamlit Session State**:
```python
# Persistent state across reruns
if 'auto_reopen_delay_minutes' not in st.session_state:
    st.session_state.auto_reopen_delay_minutes = 3

# Cache for performance
@st.cache_data(ttl=30)
def get_cached_positions():
    # Expensive operations
```

## Implementation Guidelines

1. **Maintain Visual Parity**: Strive for 1:1 visual match with Figma designs
2. **Use Existing Patterns**: Leverage established component patterns from the codebase
3. **Preserve Functionality**: Ensure all interactive elements maintain their business logic
4. **Compact UI**: Follow the established compact spacing and sizing patterns
5. **Emoji Icons**: Use the established emoji-based icon system for consistency
6. **Turkish Language**: Maintain Turkish language support for UI text
7. **Dark Theme**: Ensure designs work with the established dark theme colors

## Code Connect Integration

**File Patterns for Code Connect**:
- Main components: `app.py` (functions like `show_new_trade_page()`)
- Reusable patterns: Look for repeated UI patterns in different page functions
- Constants: `constants.py` for UI text and configuration values

**Component Mapping Strategy**:
- Map Figma components to Streamlit page functions
- Use descriptive names that match the Turkish UI labels
- Connect design tokens to the theme configuration in `.streamlit/config.toml`