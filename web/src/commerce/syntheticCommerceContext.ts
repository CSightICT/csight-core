import { operationalReference } from "../presentation/businessLabels";

export type SyntheticCommerceContext = {
  schemaVersion: "synthetic_commerce_context/1.0.0";
  customer: {
    customerId: string;
    displayName: string;
    phoneMasked: string;
    membershipTier: string;
  };
  order: {
    salesChannel: string;
    sellerName: string;
    orderedAt: string;
    productDisplayName: string;
    sku: string;
    quantity: number;
    unitPrice: string;
    merchandiseAmount: string;
    shippingFee: string;
    discountAmount: string;
    paidAmount: string;
    currency: string;
    paymentMethodMasked: string;
  };
  delivery: {
    shippingAddressRef: string;
    recipient: string;
    phoneMasked: string;
    postalCode: string;
    addressLine1: string;
    addressLine2: string;
    carrier: string;
    trackingNumberMasked: string;
    deliveredAt: string;
  };
};

type JsonRecord = Record<string, unknown>;

function record(value: unknown): JsonRecord | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : null;
}

function text(source: JsonRecord, key: string): string | null {
  const value = source[key];
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

function integer(source: JsonRecord, key: string): number | null {
  const value = source[key];
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : null;
}

function operationalAddress(value: string): string {
  return value
    .replaceAll("센텀가상로", "센텀누리로")
    .replaceAll("데모중앙로", "중앙로")
    .replaceAll("데모해안로", "해안로")
    .replaceAll("데모광장로", "광장로")
    .replaceAll("가상문화로", "문화로")
    .replaceAll("데모산업로", "산업로")
    .replaceAll("데모구", "한빛구")
    .replaceAll("가상구", "한빛구")
    .replaceAll("가상시", "다온시")
    .replaceAll("시연로", "새봄로")
    .replaceAll("데모로", "한결로")
    .replaceAll("가상동로", "다온로")
    .replaceAll("가상아파트", "해솔아파트")
    .replaceAll("시연빌라", "늘봄빌라")
    .replaceAll("시연오피스텔", "해온오피스텔")
    .replaceAll("PoC 레지던스", "마루 레지던스")
    .replaceAll("PoC 센터", "한빛 센터")
    .replaceAll("테스트파크", "해솔파크")
    .replaceAll("샘플타운", "한결타운");
}

export function readSyntheticCommerceContext(source: unknown): SyntheticCommerceContext | null {
  const root = record(source);
  const candidate = record(root?.synthetic_commerce_context ?? source);
  if (!candidate
    || candidate.schema_version !== "synthetic_commerce_context/1.0.0"
    || candidate.data_classification !== "SYNTHETIC_DEMO_ONLY") return null;
  const customer = record(candidate.customer);
  const order = record(candidate.order);
  const delivery = record(candidate.delivery);
  if (!customer || !order || !delivery) return null;

  const customerId = text(customer, "customer_id");
  const displayName = text(customer, "display_name");
  const customerPhone = text(customer, "phone_masked");
  const membershipTier = text(customer, "membership_tier");
  const salesChannel = text(order, "sales_channel");
  const sellerName = text(order, "seller_name");
  const orderedAt = text(order, "ordered_at");
  const productDisplayName = text(order, "product_display_name");
  const sku = text(order, "sku");
  const quantity = integer(order, "quantity");
  const unitPrice = text(order, "unit_price");
  const merchandiseAmount = text(order, "merchandise_amount");
  const shippingFee = text(order, "shipping_fee");
  const discountAmount = text(order, "discount_amount");
  const paidAmount = text(order, "paid_amount");
  const currency = text(order, "currency");
  const paymentMethodMasked = text(order, "payment_method_masked");
  const shippingAddressRef = text(delivery, "shipping_address_ref");
  const recipient = text(delivery, "recipient");
  const deliveryPhone = text(delivery, "phone_masked");
  const postalCode = text(delivery, "postal_code");
  const addressLine1 = text(delivery, "address_line1");
  const addressLine2 = text(delivery, "address_line2");
  const carrier = text(delivery, "carrier");
  const trackingNumberMasked = text(delivery, "tracking_number_masked");
  const deliveredAt = text(delivery, "delivered_at");
  const required = [customerId, displayName, customerPhone, membershipTier, salesChannel,
    sellerName, orderedAt, productDisplayName, sku, unitPrice, merchandiseAmount,
    shippingFee, discountAmount, paidAmount, currency, paymentMethodMasked,
    shippingAddressRef, recipient, deliveryPhone, postalCode, addressLine1, addressLine2,
    carrier, trackingNumberMasked, deliveredAt];
  if (required.some((value) => value === null) || quantity === null) return null;

  return {
    schemaVersion: "synthetic_commerce_context/1.0.0",
    customer: {
      customerId: operationalReference(customerId!), displayName: displayName!, phoneMasked: customerPhone!,
      membershipTier: membershipTier!,
    },
    order: {
      salesChannel: salesChannel!, sellerName: sellerName!, orderedAt: orderedAt!,
      productDisplayName: productDisplayName!, sku: operationalReference(sku!), quantity,
      unitPrice: unitPrice!, merchandiseAmount: merchandiseAmount!, shippingFee: shippingFee!,
      discountAmount: discountAmount!, paidAmount: paidAmount!, currency: currency!,
      paymentMethodMasked: paymentMethodMasked!,
    },
    delivery: {
      shippingAddressRef: shippingAddressRef!, recipient: recipient!, phoneMasked: deliveryPhone!,
      postalCode: postalCode!, addressLine1: operationalAddress(addressLine1!), addressLine2: operationalAddress(addressLine2!),
      carrier: carrier!, trackingNumberMasked: trackingNumberMasked!, deliveredAt: deliveredAt!,
    },
  };
}

export function formatCommerceMoney(amount: string, currency: string): string {
  const numeric = Number(amount);
  if (!Number.isFinite(numeric)) return `${amount} ${currency}`;
  try {
    return new Intl.NumberFormat("ko-KR", { style: "currency", currency, maximumFractionDigits: 0 }).format(numeric);
  } catch {
    return `${numeric.toLocaleString("ko-KR")} ${currency}`;
  }
}
