import { ListScreen } from '../../../shared/components/data-list'

const columns = [
  { key: 'name', label: 'Device' },
  { key: 'platform', label: 'Platform' },
  { key: 'owner', label: 'Owner' },
  { key: 'is_active', label: 'Active' },
  { key: 'last_used', label: 'Last used' },
]

export const DevicesPage = () => <ListScreen title="Mobile Devices" path="/api/devices" rowsKey="devices" columns={columns} />
