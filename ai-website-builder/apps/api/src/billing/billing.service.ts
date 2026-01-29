import { Injectable, BadRequestException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import Stripe from 'stripe';
import { PrismaService } from '../prisma/prisma.service';
import { SubscriptionStatus } from '@prisma/client';

@Injectable()
export class BillingService {
  private stripe: Stripe;
  private priceId: string;

  constructor(
    private configService: ConfigService,
    private prisma: PrismaService,
  ) {
    const secretKey = this.configService.get('STRIPE_SECRET_KEY');
    if (secretKey) {
      this.stripe = new Stripe(secretKey);
    }
    this.priceId = this.configService.get('STRIPE_PRICE_ID') || '';
  }

  async hasActiveSubscription(userId: string): Promise<boolean> {
    // In development without Stripe, allow all users
    if (!this.stripe) {
      return true;
    }

    const subscription = await this.prisma.stripeSubscription.findFirst({
      where: {
        userId,
        status: SubscriptionStatus.active,
      },
    });

    return !!subscription;
  }

  async getBillingStatus(userId: string) {
    const subscription = await this.prisma.stripeSubscription.findFirst({
      where: { userId },
      orderBy: { createdAt: 'desc' },
    });

    return {
      hasSubscription: !!subscription && subscription.status === SubscriptionStatus.active,
      subscription: subscription
        ? {
            status: subscription.status,
            currentPeriodEnd: subscription.currentPeriodEnd,
          }
        : null,
    };
  }

  async createCheckoutSession(userId: string, userEmail: string) {
    if (!this.stripe) {
      throw new BadRequestException('Stripe not configured');
    }

    if (!this.priceId) {
      throw new BadRequestException('Stripe price not configured');
    }

    // Check if customer already exists
    let stripeCustomerId: string;
    const existingSub = await this.prisma.stripeSubscription.findFirst({
      where: { userId },
    });

    if (existingSub) {
      stripeCustomerId = existingSub.stripeCustomerId;
    } else {
      // Create new customer
      const customer = await this.stripe.customers.create({
        email: userEmail,
        metadata: { userId },
      });
      stripeCustomerId = customer.id;
    }

    const frontendUrl = this.configService.get('FRONTEND_URL') || 'http://localhost:3000';

    // Create checkout session
    const session = await this.stripe.checkout.sessions.create({
      customer: stripeCustomerId,
      mode: 'subscription',
      payment_method_types: ['card'],
      line_items: [
        {
          price: this.priceId,
          quantity: 1,
        },
      ],
      success_url: `${frontendUrl}/dashboard?checkout=success`,
      cancel_url: `${frontendUrl}/billing?checkout=canceled`,
      metadata: { userId },
    });

    return { checkoutUrl: session.url };
  }

  async createPortalSession(userId: string) {
    if (!this.stripe) {
      throw new BadRequestException('Stripe not configured');
    }

    const subscription = await this.prisma.stripeSubscription.findFirst({
      where: { userId },
    });

    if (!subscription) {
      throw new BadRequestException('No subscription found');
    }

    const frontendUrl = this.configService.get('FRONTEND_URL') || 'http://localhost:3000';

    const session = await this.stripe.billingPortal.sessions.create({
      customer: subscription.stripeCustomerId,
      return_url: `${frontendUrl}/billing`,
    });

    return { portalUrl: session.url };
  }

  async handleWebhook(signature: string, payload: Buffer) {
    if (!this.stripe) {
      console.log('Stripe not configured, skipping webhook');
      return;
    }

    const webhookSecret = this.configService.get('STRIPE_WEBHOOK_SECRET');
    if (!webhookSecret) {
      throw new BadRequestException('Webhook secret not configured');
    }

    let event: Stripe.Event;
    try {
      event = this.stripe.webhooks.constructEvent(payload, signature, webhookSecret);
    } catch (err) {
      throw new BadRequestException(`Webhook signature verification failed: ${err}`);
    }

    console.log('Received Stripe webhook:', event.type);

    switch (event.type) {
      case 'checkout.session.completed': {
        const session = event.data.object as Stripe.Checkout.Session;
        await this.handleCheckoutCompleted(session);
        break;
      }
      case 'customer.subscription.created':
      case 'customer.subscription.updated': {
        const subscription = event.data.object as Stripe.Subscription;
        await this.handleSubscriptionUpdated(subscription);
        break;
      }
      case 'customer.subscription.deleted': {
        const subscription = event.data.object as Stripe.Subscription;
        await this.handleSubscriptionDeleted(subscription);
        break;
      }
      default:
        console.log('Unhandled webhook event:', event.type);
    }
  }

  private async handleCheckoutCompleted(session: Stripe.Checkout.Session) {
    const userId = session.metadata?.userId;
    if (!userId) {
      console.error('No userId in checkout session metadata');
      return;
    }

    if (!session.subscription || !session.customer) {
      console.error('Missing subscription or customer in checkout session');
      return;
    }

    const subscriptionId = typeof session.subscription === 'string' ? session.subscription : session.subscription.id;
    const customerId = typeof session.customer === 'string' ? session.customer : session.customer.id;

    // Fetch full subscription details
    const subscription = await this.stripe.subscriptions.retrieve(subscriptionId);

    await this.prisma.stripeSubscription.upsert({
      where: { stripeSubscriptionId: subscriptionId },
      update: {
        status: this.mapStripeStatus(subscription.status),
        currentPeriodEnd: new Date(subscription.current_period_end * 1000),
      },
      create: {
        userId,
        stripeCustomerId: customerId,
        stripeSubscriptionId: subscriptionId,
        status: this.mapStripeStatus(subscription.status),
        currentPeriodEnd: new Date(subscription.current_period_end * 1000),
      },
    });

    console.log(`Subscription created for user ${userId}`);
  }

  private async handleSubscriptionUpdated(subscription: Stripe.Subscription) {
    const existingSub = await this.prisma.stripeSubscription.findUnique({
      where: { stripeSubscriptionId: subscription.id },
    });

    if (!existingSub) {
      console.log('Subscription not found in DB, skipping update');
      return;
    }

    await this.prisma.stripeSubscription.update({
      where: { stripeSubscriptionId: subscription.id },
      data: {
        status: this.mapStripeStatus(subscription.status),
        currentPeriodEnd: new Date(subscription.current_period_end * 1000),
      },
    });

    console.log(`Subscription ${subscription.id} updated to status: ${subscription.status}`);
  }

  private async handleSubscriptionDeleted(subscription: Stripe.Subscription) {
    await this.prisma.stripeSubscription.update({
      where: { stripeSubscriptionId: subscription.id },
      data: {
        status: SubscriptionStatus.canceled,
      },
    });

    console.log(`Subscription ${subscription.id} canceled`);
  }

  private mapStripeStatus(status: Stripe.Subscription.Status): SubscriptionStatus {
    switch (status) {
      case 'active':
        return SubscriptionStatus.active;
      case 'canceled':
        return SubscriptionStatus.canceled;
      case 'past_due':
        return SubscriptionStatus.past_due;
      case 'trialing':
        return SubscriptionStatus.trialing;
      default:
        return SubscriptionStatus.incomplete;
    }
  }
}
