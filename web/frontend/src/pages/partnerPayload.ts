type PartnerPayloadInput = {
  code: string;
  name_ar: string;
  phone: string;
  address: string;
  is_customer: boolean;
  is_supplier: boolean;
  version?: number;
  is_active?: boolean;
};

export function buildPartnerPayload(input: PartnerPayloadInput) {
  return { ...input };
}
