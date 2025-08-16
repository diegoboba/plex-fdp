--report stock
create view [quantio].[report_stock] as (
select 
    p.IDPedido,
    p.IdPedidoGlobal,
    p.FechaDesde,
    p.FechaHasta,
    s.NombreFantasia as Sucursal,
    pr.razon as Proveedor,
    m.codebar,
    m.Codplex as IdProducto,
    CONCAT(ISNULL(m.Producto, ''), ' ', ISNULL(m.Presentaci, '')) AS Producto,
    st.cantidad as StockSucursales,
    v.mes as ventas_mes,
    v.anual as ventas_anual,
    v.prom as ventas_prom,
    v.dia as ventas_dia,
    vp.venta_pedido,
    sq.stock_quantio 

from quantio.plex_pedidoslineas pl 
inner join quantio.plex_pedidos p 
    on pl.IDPedido = p.IDPedido
inner join quantio.medicamentos m 
    on pl.IDProducto = m.CodPlex 
left join quantio.sucursales s 
    on s.sucursal = p.sucursal
left join quantio.plex_proveedores pr 
    on pl.IDProveedor = pr.codProve
left join quantio.plex_stock st 
    on (st.IDProducto = pl.IDProducto
    and st.sucursal = p.Sucursal)

left join quantio.ventas v 
    on (v.sucursal = p.Sucursal
    and v.IdProducto = pl.IDProducto)
left join quantio.ventas_pedido vp 
    on pl.IDPedido = vp.idpedido
    and pl.IDProducto = vp.IdProducto
    and p.sucursal = vp.Sucursal
left join quantio.stock_quantio sq 
    on sq.idProducto = pl.Idproducto


);