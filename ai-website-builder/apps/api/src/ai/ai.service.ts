import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import OpenAI from 'openai';
import {
  SiteContent,
  SiteSettings,
  Page,
  Section,
  Block,
  TextProps,
  ImageProps,
  ButtonProps,
  ListProps,
  generateId,
} from '@builder/shared';

@Injectable()
export class AiService {
  private openai: OpenAI | null;

  constructor(private configService: ConfigService) {
    const apiKey = this.configService.get('OPENAI_API_KEY');
    this.openai = apiKey ? new OpenAI({ apiKey }) : null;
  }

  async generateSiteContent(settings: SiteSettings): Promise<SiteContent> {
    // If no OpenAI key, use fallback content
    if (!this.openai) {
      console.log('No OpenAI API key, using fallback content generation');
      return this.generateFallbackContent(settings);
    }

    try {
      const homePage = await this.generateHomePage(settings);
      const contactPage = await this.generateContactPage(settings);

      return {
        pages: [homePage, contactPage],
        settings,
      };
    } catch (error) {
      console.error('AI generation failed, using fallback:', error);
      return this.generateFallbackContent(settings);
    }
  }

  private async generateHomePage(settings: SiteSettings): Promise<Page> {
    const prompt = `Generate website copy for a ${settings.industry} business called "${settings.businessName}".
Style: ${settings.stylePreset}
Primary action: ${settings.primaryCta === 'call' ? 'Call us' : settings.primaryCta === 'book' ? 'Book appointment' : 'Get a quote'}

Generate JSON with this structure:
{
  "heroHeadline": "short compelling headline (max 10 words)",
  "heroSubheadline": "supporting text (max 25 words)",
  "aboutTitle": "section title",
  "aboutText": "about paragraph (50-75 words)",
  "services": [
    { "title": "Service 1", "description": "brief description" },
    { "title": "Service 2", "description": "brief description" },
    { "title": "Service 3", "description": "brief description" }
  ],
  "testimonials": [
    { "name": "Customer Name", "quote": "brief testimonial" },
    { "name": "Customer Name", "quote": "brief testimonial" }
  ]
}

Respond ONLY with valid JSON, no markdown or explanation.`;

    const response = await this.openai!.chat.completions.create({
      model: 'gpt-3.5-turbo',
      messages: [{ role: 'user', content: prompt }],
      temperature: 0.7,
    });

    const content = response.choices[0]?.message?.content || '';
    let data;
    try {
      data = JSON.parse(content);
    } catch {
      console.error('Failed to parse AI response:', content);
      return this.createFallbackHomePage(settings);
    }

    return this.buildHomePage(settings, data);
  }

  private async generateContactPage(settings: SiteSettings): Promise<Page> {
    return {
      title: 'Contact',
      slug: 'contact',
      sections: [
        {
          id: generateId(),
          type: 'contact',
          variant: 1,
          blocks: [
            { id: generateId(), type: 'text', props: { content: 'Contact Us', variant: 'h1' } as TextProps },
            { id: generateId(), type: 'text', props: { content: `We'd love to hear from you. Reach out to ${settings.businessName} today.`, variant: 'body' } as TextProps },
            { id: generateId(), type: 'text', props: { content: `Email: ${settings.contactEmail}`, variant: 'body' } as TextProps },
            { id: generateId(), type: 'text', props: { content: `Phone: ${settings.contactPhone}`, variant: 'body' } as TextProps },
            { id: generateId(), type: 'button', props: { text: settings.primaryCta === 'call' ? 'Call Now' : settings.primaryCta === 'book' ? 'Book Appointment' : 'Request Quote', href: `tel:${settings.contactPhone}`, variant: 'primary' } as ButtonProps },
          ],
        },
        {
          id: generateId(),
          type: 'footer',
          variant: 1,
          blocks: [
            { id: generateId(), type: 'text', props: { content: `© ${new Date().getFullYear()} ${settings.businessName}. All rights reserved.`, variant: 'small' } as TextProps },
          ],
        },
      ],
    };
  }

  async generateSectionVariations(section: Section, settings: SiteSettings): Promise<Section[]> {
    // Generate 3 variations of a section
    if (!this.openai) {
      return [section, { ...section, id: generateId() }, { ...section, id: generateId() }];
    }

    const prompt = `Generate 3 variations of ${section.type} section content for a ${settings.industry} business called "${settings.businessName}".
Style: ${settings.stylePreset}

Current content: ${JSON.stringify(section.blocks.filter((b: Block) => b.type === 'text').map((b: Block) => (b.props as TextProps).content))}

Respond with JSON array of 3 variations, each with:
{ "headline": "...", "subtext": "..." }

Respond ONLY with valid JSON array.`;

    try {
      const response = await this.openai.chat.completions.create({
        model: 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.9,
      });

      const content = response.choices[0]?.message?.content || '';
      const variations = JSON.parse(content);

      return variations.map((v: { headline: string; subtext: string }, i: number) => ({
        ...section,
        id: generateId(),
        variant: (i + 1) as 1 | 2 | 3,
        blocks: section.blocks.map((block: Block) => {
          if (block.type === 'text') {
            const props = block.props as TextProps;
            if (props.variant === 'h1' || props.variant === 'h2') {
              return { ...block, id: generateId(), props: { ...props, content: v.headline } };
            }
            if (props.variant === 'body') {
              return { ...block, id: generateId(), props: { ...props, content: v.subtext } };
            }
          }
          return { ...block, id: generateId() };
        }),
      }));
    } catch (error) {
      console.error('Failed to generate variations:', error);
      return [section, { ...section, id: generateId() }, { ...section, id: generateId() }];
    }
  }

  private buildHomePage(settings: SiteSettings, data: {
    heroHeadline: string;
    heroSubheadline: string;
    aboutTitle: string;
    aboutText: string;
    services: Array<{ title: string; description: string }>;
    testimonials: Array<{ name: string; quote: string }>;
  }): Page {
    const ctaText = settings.primaryCta === 'call' ? 'Call Us Today' : settings.primaryCta === 'book' ? 'Book Now' : 'Get a Quote';

    const sections: Section[] = [
      // Hero
      {
        id: generateId(),
        type: 'hero',
        variant: 1,
        blocks: [
          { id: generateId(), type: 'text', props: { content: data.heroHeadline, variant: 'h1' } as TextProps },
          { id: generateId(), type: 'text', props: { content: data.heroSubheadline, variant: 'body' } as TextProps },
          { id: generateId(), type: 'button', props: { text: ctaText, href: '#contact', variant: 'primary' } as ButtonProps },
          { id: generateId(), type: 'image', props: { src: '/placeholder-hero.jpg', alt: 'Hero image' } as ImageProps },
        ],
      },
      // About
      {
        id: generateId(),
        type: 'about',
        variant: 1,
        blocks: [
          { id: generateId(), type: 'text', props: { content: data.aboutTitle, variant: 'h2' } as TextProps },
          { id: generateId(), type: 'text', props: { content: data.aboutText, variant: 'body' } as TextProps },
          { id: generateId(), type: 'image', props: { src: '/placeholder-about.jpg', alt: 'About us' } as ImageProps },
        ],
      },
      // Services
      {
        id: generateId(),
        type: 'services',
        variant: 1,
        blocks: [
          { id: generateId(), type: 'text', props: { content: 'Our Services', variant: 'h2' } as TextProps },
          {
            id: generateId(),
            type: 'list',
            props: {
              items: data.services.map((s) => ({ id: generateId(), title: s.title, description: s.description })),
              layout: 'grid',
            } as ListProps,
          },
        ],
      },
      // Testimonials
      {
        id: generateId(),
        type: 'testimonials',
        variant: 1,
        blocks: [
          { id: generateId(), type: 'text', props: { content: 'What Our Clients Say', variant: 'h2' } as TextProps },
          {
            id: generateId(),
            type: 'list',
            props: {
              items: data.testimonials.map((t) => ({ id: generateId(), title: t.name, description: t.quote })),
              layout: 'list',
            } as ListProps,
          },
        ],
      },
      // Contact CTA
      {
        id: generateId(),
        type: 'contact',
        variant: 1,
        blocks: [
          { id: generateId(), type: 'text', props: { content: 'Get In Touch', variant: 'h2' } as TextProps },
          { id: generateId(), type: 'text', props: { content: `Email: ${settings.contactEmail}`, variant: 'body' } as TextProps },
          { id: generateId(), type: 'text', props: { content: `Phone: ${settings.contactPhone}`, variant: 'body' } as TextProps },
          { id: generateId(), type: 'button', props: { text: ctaText, href: `tel:${settings.contactPhone}`, variant: 'primary' } as ButtonProps },
        ],
      },
      // Footer
      {
        id: generateId(),
        type: 'footer',
        variant: 1,
        blocks: [
          { id: generateId(), type: 'text', props: { content: `© ${new Date().getFullYear()} ${settings.businessName}. All rights reserved.`, variant: 'small' } as TextProps },
        ],
      },
    ];

    return {
      title: 'Home',
      slug: 'home',
      sections,
    };
  }

  private createFallbackHomePage(settings: SiteSettings): Page {
    return this.buildHomePage(settings, {
      heroHeadline: `Welcome to ${settings.businessName}`,
      heroSubheadline: `Your trusted partner in ${settings.industry.toLowerCase()}. We deliver excellence with every interaction.`,
      aboutTitle: 'About Us',
      aboutText: `${settings.businessName} has been proudly serving our community with top-quality ${settings.industry.toLowerCase()} services. Our dedicated team brings years of experience and a commitment to excellence that sets us apart.`,
      services: [
        { title: 'Professional Service', description: 'Expert solutions tailored to your needs' },
        { title: 'Quality Guaranteed', description: 'We stand behind our work with confidence' },
        { title: 'Fast Turnaround', description: 'Quick and efficient service delivery' },
      ],
      testimonials: [
        { name: 'John D.', quote: 'Exceptional service! They exceeded all my expectations.' },
        { name: 'Sarah M.', quote: 'Professional, reliable, and truly caring. Highly recommended!' },
      ],
    });
  }

  private generateFallbackContent(settings: SiteSettings): SiteContent {
    const homePage = this.createFallbackHomePage(settings);
    const contactPage: Page = {
      title: 'Contact',
      slug: 'contact',
      sections: [
        {
          id: generateId(),
          type: 'contact',
          variant: 1,
          blocks: [
            { id: generateId(), type: 'text', props: { content: 'Contact Us', variant: 'h1' } as TextProps },
            { id: generateId(), type: 'text', props: { content: `We'd love to hear from you. Reach out to ${settings.businessName} today.`, variant: 'body' } as TextProps },
            { id: generateId(), type: 'text', props: { content: `Email: ${settings.contactEmail}`, variant: 'body' } as TextProps },
            { id: generateId(), type: 'text', props: { content: `Phone: ${settings.contactPhone}`, variant: 'body' } as TextProps },
            { id: generateId(), type: 'button', props: { text: settings.primaryCta === 'call' ? 'Call Now' : settings.primaryCta === 'book' ? 'Book Appointment' : 'Request Quote', href: `tel:${settings.contactPhone}`, variant: 'primary' } as ButtonProps },
          ],
        },
        {
          id: generateId(),
          type: 'footer',
          variant: 1,
          blocks: [
            { id: generateId(), type: 'text', props: { content: `© ${new Date().getFullYear()} ${settings.businessName}. All rights reserved.`, variant: 'small' } as TextProps },
          ],
        },
      ],
    };

    return {
      pages: [homePage, contactPage],
      settings,
    };
  }
}
