
SELECT 
Pe.IDPedido,
Pe.IdPedidoGlobal,
Ss.NombreFantasia AS Sucursal,
P.Codplex AS IDProducto, 
CONCAT_WS(" ",P.Producto,P.Presentaci) AS Producto, 

TRUNCATE(SUM(IF(FC.Emision BETWEEN (DATE_SUB(CURDATE(), INTERVAL 1 MONTH)) AND CURDATE(), FL.cantidad * IF(FL.TipoCantidad="C", P.unidades, 1), 0) * IF(FC.Tipo="NC", -1, 1)) / P.unidades, 0) AS mes,
TRUNCATE(SUM((IF(FC.Emision BETWEEN (DATE_SUB(CURDATE(), INTERVAL 1 YEAR)) AND CURDATE(),FL.Cantidad, NULL) * IF(FL.TipoCantidad="C", P.Unidades, 1)) * IF(FC.Tipo="NC", -1, 1)) / P.Unidades, 0) AS anual,
(TRUNCATE(SUM(IF(FC.Emision BETWEEN (DATE_SUB(CURDATE(), INTERVAL 6 MONTH)) AND CURDATE(), FL.cantidad * IF(FL.TipoCantidad="C", P.Unidades, 1), 0) * IF(FC.Tipo="NC", -1, 1)) / P.Unidades, 0) / 6) AS prom

FROM quantio.plex_pedidoslineas PL

INNER JOIN quantio.plex_pedidos Pe USING(IDPedido)
INNER JOIN quantio.Medicamentos P ON P.CodPlex=PL.Idproducto
LEFT JOIN quantio.sucursales Ss USING(Sucursal)
LEFT JOIN quantio.factlineas FL ON FL.IDProducto=PL.IDProducto
LEFT JOIN quantio.factcabecera FC ON (FC.IDComprobante=FL.IDComprobante)

WHERE Pe.IdPedidoGlobal=40016539

AND FC.Sucursal=Pe.Sucursal 
AND FC.Tipo IN ("FV","TK","TF","NC","ND") 
AND FC.Emision BETWEEN (DATE_SUB(CURDATE(), INTERVAL 1 YEAR)) AND CURDATE()

GROUP BY PL.IDProducto
ORDER BY PL.IDProducto;

select top 10 * from quantio.factlineasptesentrega