# GitHub User Stats

[![github-user-stats](https://snapcraft.io/github-user-stats/badge.svg)](https://snapcraft.io/github-user-stats)

A self-hosted service that generates SVG stats cards for GitHub profiles, designed to be embedded in markdown READMEs. Built as a reliable replacement for `github-readme-stats.vercel.app`.

## Example

```markdown
![GitHub Stats](http://localhost:8009/api?username=kenvandine&show_icons=true&theme=dark)
```

## Quick Start

```bash
# Clone and set up
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# (Optional) Add your GitHub token for better data — see below
export GITHUB_TOKEN=ghp_your_token_here

# Start the server on port 8009
bash run.sh
```

Visit `http://localhost:8009/api?username=kenvandine&show_icons=true&theme=dark` to see it in action.

## GitHub Token (Recommended)

Without a token, the service uses GitHub's unauthenticated REST API, which has significant limitations:

| | No Token | With Token |
|---|---|---|
| **Rate limit** | 60 requests/hr | 5,000 requests/hr |
| **Contributed to** | Last ~100 events only | Lifetime total |
| **Commits** | Public repos only | Includes private repos |
| **Reviews** | Recent events only | Lifetime total |
| **API calls per user** | ~7+ REST calls | 1 GraphQL query |

### Creating a Personal Access Token

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens?type=beta) (fine-grained tokens)
2. Click **Generate new token**
3. Give it a descriptive name (e.g., `github-user-stats`)
4. Set expiration as desired
5. Under **Permissions**, no additional permissions are needed — the default read-only public access is sufficient
6. Click **Generate token**
7. Copy the token (starts with `github_pat_` for fine-grained, or `ghp_` for classic)

Alternatively, you can use a **classic token** from [github.com/settings/tokens](https://github.com/settings/tokens):
1. Click **Generate new token (classic)**
2. No scopes need to be selected — public read access is enough
3. Click **Generate token**

### Setting the Token

Set the `GITHUB_TOKEN` environment variable before starting the server:

```bash
export GITHUB_TOKEN=ghp_your_token_here
bash run.sh
```

For persistence, add it to a `.env` file or your shell profile. The token is only used server-side and is never exposed to clients.

## Username Whitelist

To control which GitHub users can be queried, the service checks an allowlist. Requests for non-listed usernames return an error SVG.

**Option 1: File** — Edit `allowed_users.txt` (one username per line). The file is re-read on each request, so changes take effect immediately without restarting:

```
kenvandine
octocat
```

**Option 2: Environment variable** — Set `ALLOWED_USERS` as a comma-separated list:

```bash
export ALLOWED_USERS=kenvandine,octocat
```

If neither is configured, all valid usernames are allowed.

## API Reference

### `GET /api`

Returns an SVG stats card.

#### Required Parameters

| Parameter | Description |
|---|---|
| `username` | GitHub username |

#### Appearance Parameters

| Parameter | Default | Description |
|---|---|---|
| `theme` | `default` | Color theme name (see [Themes](#themes)) |
| `title_color` | | Override title color (hex, no `#`) |
| `text_color` | | Override text color |
| `icon_color` | | Override icon color |
| `bg_color` | | Override background color |
| `border_color` | | Override border color |
| `show_icons` | `true` | Show stat icons |
| `hide_rank` | `false` | Hide the rank circle |
| `hide_title` | `false` | Hide the card title |
| `hide_border` | `false` | Hide the card border |
| `custom_title` | | Custom title text |
| `line_height` | `25` | Spacing between stat rows |
| `disable_animations` | `false` | Disable CSS animations |

#### Stat Visibility Parameters

| Parameter | Description |
|---|---|
| `hide` | Comma-separated list of default stats to hide |
| `show` | Comma-separated list of optional stats to show |

**Default stats** (hideable): `stars`, `commits`, `prs`, `issues`, `contribs`

**Optional stats** (via `show=`): `reviews`, `prs_merged`, `prs_merged_percentage`

#### Examples

```
# Dark theme with icons
/api?username=kenvandine&theme=dark&show_icons=true

# Show extra stats
/api?username=kenvandine&show=reviews,prs_merged,prs_merged_percentage

# Hide some stats
/api?username=kenvandine&hide=stars,issues

# Custom colors
/api?username=kenvandine&title_color=ff0000&bg_color=0d1117

# Minimal card
/api?username=kenvandine&hide_rank=true&hide_border=true&hide_title=true
```

## Themes

52 built-in themes are available:

`default`, `dark`, `radical`, `merko`, `gruvbox`, `gruvbox_light`, `tokyonight`, `onedark`, `cobalt`, `synthwave`, `highcontrast`, `dracula`, `prussian`, `monokai`, `vue`, `vue_dark`, `shades_of_purple`, `nightowl`, `buefy`, `algolia`, `great_gatsby`, `darcula`, `bear`, `solarized_dark`, `solarized_light`, `chartreuse_dark`, `nord`, `apex`, `material_palenight`, `graywhite`, `vision_friendly_dark`, `ayu_mirage`, `midnight_purple`, `calm`, `flag_india`, `omni`, `react`, `jolly`, `noctis_minimus`, `kacho_ga`, `outrun`, `ocean_dark`, `github_dark`, `github_dark_dimmed`, `transparent`, `catppuccin_latte`, `catppuccin_mocha`, `rose_pine`, `one_dark_pro`, `holi`, `neon`, `blue_green`

## Rank System

The rank circle shows a grade calculated from your stats using weighted statistical scoring:

| Grade | Percentile |
|---|---|
| S | 95%+ |
| A+ | 85-95% |
| A | 75-85% |
| A- | 60-75% |
| B+ | 50-60% |
| B | 40-50% |
| B- | 30-40% |
| C+ | 20-30% |
| C | <20% |

Stars and PRs are weighted most heavily, followed by commits, issues, reviews, and followers.

## Architecture

```
app/
├── main.py              # FastAPI app, /api endpoint, whitelist
├── github_fetcher.py    # GitHub API client (GraphQL + REST fallback)
├── stats_calculator.py  # Rank algorithm, number formatting
├── svg_renderer.py      # SVG card generation
├── cache.py             # In-memory TTL cache (30 min, stale-serving)
├── themes.py            # 52 color themes
└── icons.py             # Octicons SVG path data
```

## Caching

- Stats are cached in-memory with a 30-minute TTL
- If the GitHub API is rate-limited, stale cached data is served instead of an error
- Concurrent requests for the same username are deduplicated
- Background cleanup runs every 5 minutes

## Embedding in a README

```markdown
![My GitHub Stats](https://your-server.example.com/api?username=YOUR_USERNAME&show_icons=true&theme=dark)
```

Replace the URL with wherever you're hosting the service. The response includes `Cache-Control` and `ETag` headers for downstream caching.

## License

GPL-3.0
