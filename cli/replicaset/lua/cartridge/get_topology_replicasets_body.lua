local cartridge = require('cartridge')

local function format_topology(replicaset)
    local instances = {}
    for _, server in pairs(replicaset.servers) do
        local instance = {
            alias = server.alias,
            uuid = server.uuid,
            uri = server.uri,
        }
        table.insert(instances, instance)
    end

    local leader_uuid
    if replicaset.active_master ~= nil then
        leader_uuid = replicaset.active_master.uuid
    end

    local topology_replicaset = {
        uuid = replicaset.uuid,
        leaderuuid = leader_uuid,
        alias = replicaset.alias,
        roles = replicaset.roles,
        instances = instances,
    }

    return topology_replicaset
end

local topology_replicasets = {}

local replicasets, err = cartridge.admin_get_replicasets()

if err ~= nil then
    err = err.err
end

assert(err == nil, tostring(err))

for _, replicaset in pairs(replicasets) do
    local topology_replicaset = format_topology(replicaset)
    table.insert(topology_replicasets, topology_replicaset)
end

local failover_params = require('cartridge').failover_get_params()
return {
    failover = failover_params.mode,
    provider = failover_params.state_provider or "none",
    replicasets = topology_replicasets,
}
