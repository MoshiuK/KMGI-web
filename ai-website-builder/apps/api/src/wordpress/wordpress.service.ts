import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { exec } from 'child_process';
import { promisify } from 'util';
import { SiteContent, Page, Section, Block, TextProps, ImageProps, ButtonProps, ListProps, ListItem } from '@builder/shared';

const execAsync = promisify(exec);

interface Site {
  id: string;
  name: string;
  owner: { email: string };
  tenant: { slug: string };
}

interface ProvisionResult {
  wpSiteId: number;
  wpAdminUrl: string;
  wpSiteUrl: string;
}

@Injectable()
export class WordPressService {
  private wpCliPath: string;
  private wpMultisiteUrl: string;

  constructor(private configService: ConfigService) {
    this.wpCliPath = this.configService.get('WP_CLI_PATH') || 'wp';
    this.wpMultisiteUrl = this.configService.get('WP_MULTISITE_URL') || 'http://localhost:8080';
  }

  private async runWpCli(command: string): Promise<string> {
    const wpPath = this.configService.get('WP_PATH') || '/var/www/html';
    const fullCommand = `${this.wpCliPath} ${command} --path=${wpPath} --allow-root`;

    try {
      const { stdout, stderr } = await execAsync(fullCommand, {
        env: { ...process.env },
        timeout: 60000,
      });
      if (stderr && !stderr.includes('Warning')) {
        console.error('WP-CLI stderr:', stderr);
      }
      return stdout.trim();
    } catch (error) {
      console.error('WP-CLI error:', error);
      throw error;
    }
  }

  async provisionSite(site: Site): Promise<ProvisionResult> {
    // Generate slug from site name
    const slug = site.name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '')
      .substring(0, 50);

    const siteSlug = `${slug}-${site.id.substring(0, 8)}`;
    const siteUrl = `${this.wpMultisiteUrl}/${siteSlug}`;
    const adminEmail = site.owner.email;
    const siteTitle = site.name;

    try {
      // Create the subsite
      const createOutput = await this.runWpCli(
        `site create --slug="${siteSlug}" --title="${siteTitle}" --email="${adminEmail}" --porcelain`,
      );

      const wpSiteId = parseInt(createOutput, 10);
      if (isNaN(wpSiteId)) {
        throw new Error(`Failed to parse site ID from output: ${createOutput}`);
      }

      return {
        wpSiteId,
        wpAdminUrl: `${siteUrl}/wp-admin`,
        wpSiteUrl: siteUrl,
      };
    } catch (error) {
      // In dev mode, simulate WP site creation
      if (this.configService.get('NODE_ENV') === 'development') {
        console.log('DEV MODE: Simulating WordPress site creation');
        const mockSiteId = Math.floor(Math.random() * 10000);
        return {
          wpSiteId: mockSiteId,
          wpAdminUrl: `${this.wpMultisiteUrl}/${siteSlug}/wp-admin`,
          wpSiteUrl: `${this.wpMultisiteUrl}/${siteSlug}`,
        };
      }
      throw error;
    }
  }

  async applyThemeAndPlugins(wpSiteId: number): Promise<void> {
    try {
      // Switch to the site context
      const urlFlag = `--url=${this.wpMultisiteUrl}/?blog_id=${wpSiteId}`;

      // Activate a clean theme (Twenty Twenty-Four or similar)
      await this.runWpCli(`theme activate twentytwentyfour ${urlFlag}`);

      // Optional: Install and activate a simple page builder plugin if needed
      // For MVP, we'll use plain Gutenberg blocks

      console.log(`Theme and plugins applied for site ${wpSiteId}`);
    } catch (error) {
      // In dev mode, just log
      if (this.configService.get('NODE_ENV') === 'development') {
        console.log('DEV MODE: Simulating theme/plugin setup');
        return;
      }
      throw error;
    }
  }

  async publishVersion(wpSiteId: number, content: SiteContent): Promise<void> {
    try {
      const urlFlag = `--url=${this.wpMultisiteUrl}/?blog_id=${wpSiteId}`;

      for (const page of content.pages) {
        const htmlContent = this.compilePageToHtml(page, content.settings.accentColor);
        const gutenbergBlocks = this.compilePageToGutenberg(page, content.settings.accentColor);

        // Check if page exists
        const existingPages = await this.runWpCli(
          `post list --post_type=page --name="${page.slug}" --format=ids ${urlFlag}`,
        );

        if (existingPages) {
          // Update existing page
          const pageId = existingPages.split(' ')[0];
          await this.runWpCli(
            `post update ${pageId} --post_content='${this.escapeShell(gutenbergBlocks)}' --post_status=publish ${urlFlag}`,
          );
        } else {
          // Create new page
          await this.runWpCli(
            `post create --post_type=page --post_title="${page.title}" --post_name="${page.slug}" --post_content='${this.escapeShell(gutenbergBlocks)}' --post_status=publish ${urlFlag}`,
          );
        }
      }

      // Set home page
      const homePage = content.pages.find((p: Page) => p.slug === 'home');
      if (homePage) {
        const homePageId = await this.runWpCli(
          `post list --post_type=page --name="home" --format=ids ${urlFlag}`,
        );
        if (homePageId) {
          await this.runWpCli(`option update show_on_front page ${urlFlag}`);
          await this.runWpCli(`option update page_on_front ${homePageId.split(' ')[0]} ${urlFlag}`);
        }
      }

      console.log(`Published ${content.pages.length} pages to WordPress site ${wpSiteId}`);
    } catch (error) {
      // In dev mode, just log
      if (this.configService.get('NODE_ENV') === 'development') {
        console.log('DEV MODE: Simulating publish to WordPress');
        console.log('Pages to publish:', content.pages.map((p: Page) => p.title));
        return;
      }
      throw error;
    }
  }

  private escapeShell(str: string): string {
    return str.replace(/'/g, "'\\''");
  }

  private compilePageToHtml(page: Page, accentColor: string): string {
    return page.sections.map((section: Section) => this.compileSectionToHtml(section, accentColor)).join('\n');
  }

  private compilePageToGutenberg(page: Page, accentColor: string): string {
    return page.sections.map((section: Section) => this.compileSectionToGutenberg(section, accentColor)).join('\n\n');
  }

  private compileSectionToHtml(section: Section, accentColor: string): string {
    const blocks = section.blocks.map((block: Block) => this.compileBlockToHtml(block, accentColor)).join('\n');
    return `<section class="wp-block-group section-${section.type}" data-section-id="${section.id}">${blocks}</section>`;
  }

  private compileSectionToGutenberg(section: Section, accentColor: string): string {
    const blocks = section.blocks.map((block: Block) => this.compileBlockToGutenberg(block, accentColor)).join('\n');
    return `<!-- wp:group {"className":"section-${section.type}"} -->\n<div class="wp-block-group section-${section.type}">${blocks}</div>\n<!-- /wp:group -->`;
  }

  private compileBlockToHtml(block: Block, accentColor: string): string {
    switch (block.type) {
      case 'text': {
        const props = block.props as TextProps;
        const tag = this.getTextTag(props.variant);
        return `<${tag}>${this.escapeHtml(props.content)}</${tag}>`;
      }
      case 'image': {
        const props = block.props as ImageProps;
        return `<figure class="wp-block-image"><img src="${props.src}" alt="${this.escapeHtml(props.alt)}" /></figure>`;
      }
      case 'button': {
        const props = block.props as ButtonProps;
        const bgColor = props.variant === 'primary' ? accentColor : 'transparent';
        const textColor = props.variant === 'primary' ? '#ffffff' : accentColor;
        return `<div class="wp-block-button"><a class="wp-block-button__link" href="${props.href}" style="background-color:${bgColor};color:${textColor}">${this.escapeHtml(props.text)}</a></div>`;
      }
      case 'list': {
        const props = block.props as ListProps;
        const items = props.items
          .map((item: ListItem) => `<li><strong>${this.escapeHtml(item.title)}</strong><p>${this.escapeHtml(item.description)}</p></li>`)
          .join('');
        return `<ul class="wp-block-list layout-${props.layout}">${items}</ul>`;
      }
      default:
        return '';
    }
  }

  private compileBlockToGutenberg(block: Block, accentColor: string): string {
    switch (block.type) {
      case 'text': {
        const props = block.props as TextProps;
        switch (props.variant) {
          case 'h1':
            return `<!-- wp:heading {"level":1} -->\n<h1 class="wp-block-heading">${this.escapeHtml(props.content)}</h1>\n<!-- /wp:heading -->`;
          case 'h2':
            return `<!-- wp:heading -->\n<h2 class="wp-block-heading">${this.escapeHtml(props.content)}</h2>\n<!-- /wp:heading -->`;
          case 'h3':
            return `<!-- wp:heading {"level":3} -->\n<h3 class="wp-block-heading">${this.escapeHtml(props.content)}</h3>\n<!-- /wp:heading -->`;
          case 'small':
            return `<!-- wp:paragraph {"fontSize":"small"} -->\n<p class="has-small-font-size">${this.escapeHtml(props.content)}</p>\n<!-- /wp:paragraph -->`;
          default:
            return `<!-- wp:paragraph -->\n<p>${this.escapeHtml(props.content)}</p>\n<!-- /wp:paragraph -->`;
        }
      }
      case 'image': {
        const props = block.props as ImageProps;
        return `<!-- wp:image -->\n<figure class="wp-block-image"><img src="${props.src}" alt="${this.escapeHtml(props.alt)}"/></figure>\n<!-- /wp:image -->`;
      }
      case 'button': {
        const props = block.props as ButtonProps;
        const bgColor = props.variant === 'primary' ? accentColor : 'transparent';
        return `<!-- wp:buttons -->\n<div class="wp-block-buttons"><!-- wp:button {"backgroundColor":"${bgColor}"} -->\n<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="${props.href}">${this.escapeHtml(props.text)}</a></div>\n<!-- /wp:button --></div>\n<!-- /wp:buttons -->`;
      }
      case 'list': {
        const props = block.props as ListProps;
        const items = props.items.map((item: ListItem) => `<li><strong>${this.escapeHtml(item.title)}</strong> - ${this.escapeHtml(item.description)}</li>`).join('');
        return `<!-- wp:list -->\n<ul class="wp-block-list">${items}</ul>\n<!-- /wp:list -->`;
      }
      default:
        return '';
    }
  }

  private getTextTag(variant: string): string {
    switch (variant) {
      case 'h1':
        return 'h1';
      case 'h2':
        return 'h2';
      case 'h3':
        return 'h3';
      case 'small':
        return 'small';
      default:
        return 'p';
    }
  }

  private escapeHtml(str: string): string {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
}
