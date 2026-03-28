// Shared finance demo data - deterministic and testable
// All IDs and values are stable for Predicate runtime verification

export interface Invoice {
  id: string;
  vendor: string;
  vendorId: string;
  amount: number;
  currency: string;
  dueDate: string;
  invoiceDate: string;
  status: 'pending' | 'reconciled' | 'needs_review';
  paymentStatus: 'unpaid' | 'scheduled' | 'paid';
  priority: 'high' | 'medium' | 'low';
  poReference: string;
  mismatch: boolean;
  mismatchReason?: string;
  notes: ActivityNote[];
}

export interface VendorRecord {
  id: string;
  vendorName: string;
  vendorLegalName: string;
  invoiceNumber: string;
  billedAmount: number;
  currency: string;
  invoiceDate: string;
  paymentState: string;
  contactEmail: string;
  address: string;
}

export interface ActivityNote {
  author: string;
  timestamp: string;
  text: string;
}

// Main invoice data - used across queue and detail pages
export const INVOICES: Invoice[] = [
  {
    id: 'INV-2024-001',
    vendor: 'Acme Corp',
    vendorId: 'VENDOR-001',
    amount: 12500.0,
    currency: 'USD',
    dueDate: '2024-04-15',
    invoiceDate: '2024-03-15',
    status: 'pending',
    paymentStatus: 'unpaid',
    priority: 'high',
    poReference: 'PO-8821',
    mismatch: false,
    notes: [
      {
        author: 'System',
        timestamp: '2024-03-15 09:00',
        text: 'Invoice received and logged.',
      },
    ],
  },
  {
    id: 'INV-2024-002',
    vendor: 'TechSupply Inc',
    vendorId: 'VENDOR-002',
    amount: 8750.5,
    currency: 'USD',
    dueDate: '2024-04-18',
    invoiceDate: '2024-03-18',
    status: 'pending',
    paymentStatus: 'unpaid',
    priority: 'medium',
    poReference: 'PO-8834',
    mismatch: true,
    mismatchReason: 'Vendor name mismatch: "TechSupply Inc" vs "Tech Supply Inc."',
    notes: [
      {
        author: 'System',
        timestamp: '2024-03-18 10:15',
        text: 'Invoice received and logged.',
      },
      {
        author: 'System',
        timestamp: '2024-03-18 10:16',
        text: 'Warning: Vendor name mismatch detected.',
      },
    ],
  },
  {
    id: 'INV-2024-003',
    vendor: 'Global Services LLC',
    vendorId: 'VENDOR-003',
    amount: 45000.0,
    currency: 'USD',
    dueDate: '2024-04-10',
    invoiceDate: '2024-03-10',
    status: 'pending',
    paymentStatus: 'unpaid',
    priority: 'high',
    poReference: 'PO-8799',
    mismatch: false,
    notes: [
      {
        author: 'System',
        timestamp: '2024-03-10 08:30',
        text: 'Invoice received and logged.',
      },
    ],
  },
  {
    id: 'INV-2024-004',
    vendor: 'Office Essentials',
    vendorId: 'VENDOR-004',
    amount: 2340.25,
    currency: 'USD',
    dueDate: '2024-04-22',
    invoiceDate: '2024-03-22',
    status: 'reconciled',
    paymentStatus: 'scheduled',
    priority: 'low',
    poReference: 'PO-8845',
    mismatch: false,
    notes: [
      {
        author: 'System',
        timestamp: '2024-03-22 11:00',
        text: 'Invoice received and logged.',
      },
      {
        author: 'Agent',
        timestamp: '2024-03-23 14:00',
        text: 'Reconciliation completed. All fields match.',
      },
    ],
  },
  {
    id: 'INV-2024-005',
    vendor: 'Cloud Hosting Pro',
    vendorId: 'VENDOR-005',
    amount: 15890.0,
    currency: 'USD',
    dueDate: '2024-04-12',
    invoiceDate: '2024-03-12',
    status: 'needs_review',
    paymentStatus: 'unpaid',
    priority: 'high',
    poReference: 'PO-8812',
    mismatch: true,
    mismatchReason: 'Amount mismatch: Invoice $15,890.00 vs PO $15,000.00',
    notes: [
      {
        author: 'System',
        timestamp: '2024-03-12 09:45',
        text: 'Invoice received and logged.',
      },
      {
        author: 'System',
        timestamp: '2024-03-12 09:46',
        text: 'Warning: Amount exceeds PO by $890.00.',
      },
      {
        author: 'Agent',
        timestamp: '2024-04-08 14:32',
        text: 'Routed to review queue: amount mismatch requires approval.',
      },
    ],
  },
];

// Vendor records - simulates data from external vendor portal
// Note: Some intentional mismatches for demo purposes
export const VENDOR_RECORDS: VendorRecord[] = [
  {
    id: 'VENDOR-001',
    vendorName: 'Acme Corp',
    vendorLegalName: 'Acme Corporation',
    invoiceNumber: 'INV-2024-001',
    billedAmount: 12500.0,
    currency: 'USD',
    invoiceDate: '2024-03-15',
    paymentState: 'Awaiting Payment',
    contactEmail: 'billing@acmecorp.com',
    address: '123 Industrial Way, Chicago, IL 60601',
  },
  {
    id: 'VENDOR-002',
    vendorName: 'Tech Supply Inc.',  // Note: intentional mismatch with "TechSupply Inc"
    vendorLegalName: 'Tech Supply Incorporated',
    invoiceNumber: 'INV-2024-002',
    billedAmount: 8750.5,
    currency: 'USD',
    invoiceDate: '2024-03-18',
    paymentState: 'Awaiting Payment',
    contactEmail: 'accounts@techsupply.com',
    address: '456 Tech Park, San Jose, CA 95110',
  },
  {
    id: 'VENDOR-003',
    vendorName: 'Global Services LLC',
    vendorLegalName: 'Global Services Limited Liability Company',
    invoiceNumber: 'INV-2024-003',
    billedAmount: 45000.0,
    currency: 'USD',
    invoiceDate: '2024-03-10',
    paymentState: 'Awaiting Payment',
    contactEmail: 'invoices@globalservices.com',
    address: '789 Commerce St, New York, NY 10001',
  },
  {
    id: 'VENDOR-004',
    vendorName: 'Office Essentials',
    vendorLegalName: 'Office Essentials Corp',
    invoiceNumber: 'INV-2024-004',
    billedAmount: 2340.25,
    currency: 'USD',
    invoiceDate: '2024-03-22',
    paymentState: 'Payment Scheduled',
    contactEmail: 'billing@officeessentials.com',
    address: '321 Supply Blvd, Dallas, TX 75201',
  },
  {
    id: 'VENDOR-005',
    vendorName: 'Cloud Hosting Pro',
    vendorLegalName: 'Cloud Hosting Professional Services Inc',
    invoiceNumber: 'INV-2024-005',
    billedAmount: 15890.0,  // Matches invoice (mismatch is with PO, not vendor record)
    currency: 'USD',
    invoiceDate: '2024-03-12',
    paymentState: 'Awaiting Payment',
    contactEmail: 'finance@cloudhostingpro.com',
    address: '555 Cloud Ave, Seattle, WA 98101',
  },
];

// Lookup helpers
export function getInvoiceById(id: string): Invoice | undefined {
  return INVOICES.find((inv) => inv.id === id);
}

export function getVendorById(id: string): VendorRecord | undefined {
  return VENDOR_RECORDS.find((v) => v.id === id);
}

export function getVendorByInvoiceId(invoiceId: string): VendorRecord | undefined {
  return VENDOR_RECORDS.find((v) => v.invoiceNumber === invoiceId);
}

// Format helpers
export function formatCurrency(amount: number, currency: string = 'USD'): string {
  return `$${amount.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
}
