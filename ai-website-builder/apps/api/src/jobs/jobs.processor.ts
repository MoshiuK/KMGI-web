import { Injectable, OnModuleInit, Inject, forwardRef } from '@nestjs/common';
import { Worker, Job } from 'bullmq';
import { ConfigService } from '@nestjs/config';
import { PrismaService } from '../prisma/prisma.service';
import { JobsService } from './jobs.service';
import { WordPressService } from '../wordpress/wordpress.service';
import { AiService } from '../ai/ai.service';
import { JobStatus, SiteStatus } from '@prisma/client';
import { SiteContent } from '@builder/shared';

interface JobData {
  jobId: string;
  siteId: string;
  type: string;
  metadata?: Record<string, unknown>;
}

@Injectable()
export class JobsProcessor implements OnModuleInit {
  private worker!: Worker;

  constructor(
    private configService: ConfigService,
    private prisma: PrismaService,
    private jobsService: JobsService,
    @Inject(forwardRef(() => WordPressService))
    private wordpressService: WordPressService,
    @Inject(forwardRef(() => AiService))
    private aiService: AiService,
  ) {}

  onModuleInit() {
    const redisHost = this.configService.get('REDIS_HOST') || 'localhost';
    const redisPort = this.configService.get('REDIS_PORT') || 6379;

    this.worker = new Worker(
      'site-jobs',
      async (job: Job<JobData>) => {
        await this.processJob(job.data);
      },
      {
        connection: {
          host: redisHost,
          port: Number(redisPort),
        },
      },
    );

    this.worker.on('completed', (job) => {
      console.log(`Job ${job.id} completed`);
    });

    this.worker.on('failed', (job, err) => {
      console.error(`Job ${job?.id} failed:`, err);
    });

    console.log('Job processor started');
  }

  private async processJob(data: JobData) {
    const { jobId, siteId, type, metadata } = data;

    try {
      await this.jobsService.updateJobStatus(jobId, JobStatus.running);
      await this.jobsService.addJobLog(jobId, `Starting ${type} job`);

      switch (type) {
        case 'provision':
          await this.handleProvision(jobId, siteId, metadata);
          break;
        case 'generate':
          await this.handleGenerate(jobId, siteId, metadata);
          break;
        case 'publish':
          await this.handlePublish(jobId, siteId, metadata);
          break;
        case 'rollback':
          await this.handleRollback(jobId, siteId, metadata);
          break;
        default:
          throw new Error(`Unknown job type: ${type}`);
      }

      await this.jobsService.updateJobStatus(jobId, JobStatus.completed);
      await this.jobsService.addJobLog(jobId, `Job completed successfully`);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      await this.jobsService.updateJobStatus(jobId, JobStatus.failed, errorMessage);
      await this.jobsService.addJobLog(jobId, `Job failed: ${errorMessage}`);
      throw error;
    }
  }

  private async handleProvision(jobId: string, siteId: string, metadata?: Record<string, unknown>) {
    await this.jobsService.addJobLog(jobId, 'Provisioning WordPress site...');

    // Update site status
    await this.prisma.site.update({
      where: { id: siteId },
      data: { status: SiteStatus.provisioning },
    });

    // Get site details
    const site = await this.prisma.site.findUnique({
      where: { id: siteId },
      include: { owner: true, tenant: true },
    });

    if (!site) {
      throw new Error('Site not found');
    }

    // Provision WordPress site
    const wpResult = await this.wordpressService.provisionSite(site);
    await this.jobsService.addJobLog(jobId, `WordPress site created: ${wpResult.wpSiteUrl}`);

    // Update site with WP details
    await this.prisma.site.update({
      where: { id: siteId },
      data: {
        wpSiteId: wpResult.wpSiteId,
        wpAdminUrl: wpResult.wpAdminUrl,
        wpSiteUrl: wpResult.wpSiteUrl,
        status: SiteStatus.generating,
      },
    });

    // Apply theme and plugins
    await this.wordpressService.applyThemeAndPlugins(wpResult.wpSiteId);
    await this.jobsService.addJobLog(jobId, 'Theme and plugins applied');

    // Automatically trigger AI generation
    await this.handleGenerate(jobId, siteId, metadata);
  }

  private async handleGenerate(jobId: string, siteId: string, metadata?: Record<string, unknown>) {
    await this.jobsService.addJobLog(jobId, 'Generating content with AI...');

    // Get site with latest version
    const site = await this.prisma.site.findUnique({
      where: { id: siteId },
      include: {
        versions: {
          orderBy: { versionNumber: 'desc' },
          take: 1,
        },
      },
    });

    if (!site) {
      throw new Error('Site not found');
    }

    // Get settings from metadata or latest version
    const existingContent = site.versions[0]?.pageJson as SiteContent | undefined;
    const settings = (metadata?.settings || existingContent?.settings) as SiteContent['settings'];

    if (!settings) {
      throw new Error('No settings found for generation');
    }

    // Generate content with AI
    const content = await this.aiService.generateSiteContent(settings);
    await this.jobsService.addJobLog(jobId, 'AI content generated');

    // Get next version number
    const maxVersion = await this.prisma.siteVersion.findFirst({
      where: { siteId },
      orderBy: { versionNumber: 'desc' },
    });
    const nextVersion = (maxVersion?.versionNumber || 0) + 1;

    // Create new version
    const version = await this.prisma.siteVersion.create({
      data: {
        siteId,
        versionNumber: nextVersion,
        pageJson: content as object,
      },
    });
    await this.jobsService.addJobLog(jobId, `Version ${nextVersion} created`);

    // Update site
    await this.prisma.site.update({
      where: { id: siteId },
      data: {
        status: SiteStatus.draft,
        currentVersionId: version.id,
      },
    });
  }

  private async handlePublish(jobId: string, siteId: string, _metadata?: Record<string, unknown>) {
    await this.jobsService.addJobLog(jobId, 'Publishing to WordPress...');

    const site = await this.prisma.site.findUnique({
      where: { id: siteId },
    });

    if (!site) {
      throw new Error('Site not found');
    }

    if (!site.currentVersionId) {
      throw new Error('No current version to publish');
    }

    if (!site.wpSiteId) {
      throw new Error('WordPress site not provisioned');
    }

    // Get current version
    const version = await this.prisma.siteVersion.findUnique({
      where: { id: site.currentVersionId },
    });

    if (!version) {
      throw new Error('Version not found');
    }

    // Publish to WordPress
    await this.wordpressService.publishVersion(site.wpSiteId, version.pageJson as SiteContent);
    await this.jobsService.addJobLog(jobId, 'Content published to WordPress');

    // Update site status
    await this.prisma.site.update({
      where: { id: siteId },
      data: {
        status: SiteStatus.published,
        publishedVersionId: version.id,
      },
    });
  }

  private async handleRollback(jobId: string, siteId: string, metadata?: Record<string, unknown>) {
    const versionId = metadata?.versionId as string;
    if (!versionId) {
      throw new Error('Version ID required for rollback');
    }

    await this.jobsService.addJobLog(jobId, `Rolling back to version ${versionId}...`);

    const site = await this.prisma.site.findUnique({
      where: { id: siteId },
    });

    if (!site) {
      throw new Error('Site not found');
    }

    if (!site.wpSiteId) {
      throw new Error('WordPress site not provisioned');
    }

    // Get target version
    const version = await this.prisma.siteVersion.findUnique({
      where: { id: versionId },
    });

    if (!version || version.siteId !== siteId) {
      throw new Error('Version not found');
    }

    // Publish old version to WordPress
    await this.wordpressService.publishVersion(site.wpSiteId, version.pageJson as SiteContent);
    await this.jobsService.addJobLog(jobId, 'Rolled back content published');

    // Update site
    await this.prisma.site.update({
      where: { id: siteId },
      data: {
        currentVersionId: version.id,
        publishedVersionId: version.id,
        status: SiteStatus.published,
      },
    });
  }
}
