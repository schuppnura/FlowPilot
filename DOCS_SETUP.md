# FlowPilot Documentation Setup

MkDocs has been successfully configured for FlowPilot! 🎉

## What Was Set Up

### 1. MkDocs Material Theme
- Professional documentation site with Material Design
- Dark/light mode support
- Full-text search
- Mobile-responsive design
- Code syntax highlighting
- Tabbed content support

### 2. OpenAPI Integration
- Embedded Swagger UI for all API specifications
- Interactive API documentation directly in the docs
- All OpenAPI specs automatically rendered

### 3. Documentation Structure

```
docs/
├── index.md                    # Homepage with feature overview
├── getting-started/
│   ├── quick-start.md         # ✅ Complete - 5-minute setup guide
│   ├── local-development.md   # Placeholder
│   └── gcp-deployment.md      # Placeholder
├── architecture/               # Placeholders for architecture docs
├── deployment/                 # Placeholders for deployment guides
├── development/                # Placeholders for dev guides
├── api/
│   ├── authz.md               # ✅ Complete - AuthZ API with examples
│   ├── domain-services.md     # ✅ With OpenAPI embed
│   ├── delegation.md          # ✅ With OpenAPI embed
│   └── ai-agent.md            # ✅ With OpenAPI embed
├── guides/                     # Placeholders for how-to guides
└── contributing/               # Placeholders for contribution docs
```

### 4. Scripts Created

- **`serve-docs.sh`** - Serve documentation locally at http://127.0.0.1:8000
- **`deploy-docs.sh`** - Deploy to GitHub Pages automatically
- **`docs/README.md`** - Documentation about the documentation

## Usage

### View Documentation Locally

```bash
./serve-docs.sh
```

Or directly:

```bash
export PATH="$HOME/Library/Python/3.9/bin:$PATH"
mkdocs serve
```

Visit: http://127.0.0.1:8000

### Build Static Site

```bash
mkdocs build
```

Output will be in the `site/` directory.

### Deploy to GitHub Pages

```bash
./deploy-docs.sh
```

Or directly:

```bash
mkdocs gh-deploy
```

## Next Steps

### 1. Populate Placeholder Pages

Many pages are currently placeholders. You can populate them by:

1. Converting existing documentation from:
   - `README.md` (architecture and overview)
   - `WARP.md` (development commands and patterns)
   - `SECURITY.md` (security details)
   - `GCP_MIGRATION.md` (deployment guides)

2. Creating new content:
   - Architecture diagrams
   - Step-by-step tutorials
   - Policy writing guides
   - Troubleshooting FAQs

### 2. Update Repository URLs

In `mkdocs.yml`, update:

```yaml
repo_url: https://github.com/yourusername/flowpilot  # Your actual repo
site_url: https://flowpilot.dev  # Your actual domain
```

### 3. Configure GitHub Pages

If using GitHub Pages:

1. Go to repository Settings → Pages
2. Source: Deploy from a branch
3. Branch: `gh-pages` (created automatically by `mkdocs gh-deploy`)
4. Your docs will be at: `https://yourusername.github.io/flowpilot/`

### 4. Customize Theme (Optional)

Edit `mkdocs.yml` to:
- Change color scheme (`primary`, `accent`)
- Add logo and favicon
- Add social links
- Configure navigation

### 5. Add More Features (Optional)

Consider adding:
- **mkdocs-mermaid2-plugin** - For diagrams
- **mkdocs-pdf-export-plugin** - Generate PDF docs
- **mkdocs-git-revision-date-localized-plugin** - Show last update dates
- **mkdocs-minify-plugin** - Minify HTML/CSS/JS

## Key Features

### ✅ What Works Now

1. **Homepage** - Professional landing page with feature cards
2. **Quick Start** - Complete getting started guide
3. **API Reference** - All 4 APIs with embedded Swagger UI
4. **Search** - Full-text search across all pages
5. **Responsive** - Works on mobile, tablet, desktop
6. **Dark Mode** - Auto dark/light mode switching

### 🚧 What Needs Content

- Architecture overview pages
- Deployment guides (expand on placeholders)
- Development workflow guides
- Policy writing tutorials
- Contributing guidelines
- Troubleshooting guide

## File Locations

- **Config**: `mkdocs.yml` (root)
- **Content**: `docs/` directory
- **OpenAPI specs**: `docs/flowpilot-openapi/` (copied from root)
- **Build output**: `site/` (gitignored)

## Tips

### Writing Documentation

- Use Markdown format
- Add code examples with syntax highlighting:
  ````markdown
  ```python
  code here
  ```
  ````

- Use admonitions for notes/warnings:
  ```markdown
  !!! note "Title"
      Content here
  ```

- Create tabs for multi-option content:
  ```markdown
  === "Option 1"
      Content
  === "Option 2"
      Content
  ```

### Testing Changes

Always test locally before deploying:

```bash
mkdocs serve
# Check http://127.0.0.1:8000
# Make changes, auto-reloads
```

### Linking Between Pages

Use relative links:

```markdown
[Link text](../architecture/overview.md)
```

## Installed Packages

- `mkdocs-material==9.7.1` - Material theme
- `mkdocs-swagger-ui-tag==0.7.2` - Swagger UI integration
- `mkdocs==1.6.1` - Core MkDocs

## Resources

- [MkDocs Material Documentation](https://squidfunk.github.io/mkdocs-material/)
- [MkDocs Documentation](https://www.mkdocs.org/)
- [Swagger UI Tag Plugin](https://github.com/blueswen/mkdocs-swagger-ui-tag)

## Support

For issues or questions:
1. Check the [MkDocs Material docs](https://squidfunk.github.io/mkdocs-material/)
2. Review `docs/README.md` for contribution guidelines
3. Test locally with `mkdocs serve` before deploying

Happy documenting! 📚
